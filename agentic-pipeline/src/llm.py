"""The one place the app talks to a language model.

  make_client()                          the client for LLM_PROVIDER ("bullsai" by default; "anthropic" is a thin extra)
  complete(client, system, messages, max_tokens, model=None, schema=None) -> LLMResult(text, input_tokens, output_tokens, model)
  complete_json(client, ..., schema)     -> (data, usage): fences and reasoning text stripped, one retry, then LLMError
  cost_of(usage, model) / cost_tracked(model)   per-model prices live in PRICES below

Env (read from .env, never printed): LLM_PROVIDER, BULLSAI_API_KEY, BULLSAI_BASE_URL, BULLSAI_MODEL,
BULLSAI_REWRITE_MODEL (helper model; defaults to BULLSAI_MODEL),
BULLSAI_REASONING_EFFORT (optional: low|medium|high, for models that support it; unset = not sent),
BULLSAI_THINKING ("default" = leave the gateway's setting, the default; "off" = send thinking disabled, which the gateway ignored on long prompts). Only for provider "anthropic": ANTHROPIC_API_KEY, LLM_MODEL.
"""
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]

# $ per million tokens (input, output). BullsAI is a course key with no known price, so its models are NOT listed:
# an unlisted model costs 0 and the screens say "course key, cost not tracked".
PRICES = {"claude-sonnet-5-5": (2.0, 10.0), "claude-sonnet-5": (2.0, 10.0), "claude-opus-5-5": (4.0, 20.0),
          "claude-opus-5": (5.0, 25.0), "claude-haiku-4-5": (1.0, 5.0), "claude-haiku-4-5-20251001": (1.0, 5.0),
          "claude-fable-5-1": (10.0, 50.0)}
DEFAULT_BULLSAI_MODEL = "google/gemma-4-31B-it"      # chosen 2026-10-19: fastest and accurate on the 8-question check
CONNECT_TIMEOUT = 10.0
NOT_TRACKED = "course key, cost not tracked"


class LLMError(RuntimeError):
    """Any model failure (network, key, model name, bad output). `fatal` = every further call would fail too."""

    def __init__(self, message, fatal=False):
        super().__init__(message)
        self.fatal = fatal


class EmptyAnswer(LLMError):
    """The model returned no text (for example its reasoning used up the token limit)."""


EMPTY_MESSAGE = "The model returned no answer. Please try again."


@dataclass
class LLMResult:
    text: str
    input_tokens: int
    output_tokens: int
    model: str = ""

    @property
    def usage(self):
        return {"input_tokens": self.input_tokens, "output_tokens": self.output_tokens}


def provider():
    load_dotenv(ROOT / ".env")
    return (os.environ.get("LLM_PROVIDER") or "bullsai").strip().lower()


def default_model():
    provider_ = provider()
    if provider_ == "anthropic":
        return os.environ.get("LLM_MODEL") or "claude-sonnet-5-5"
    return os.environ.get("BULLSAI_MODEL") or DEFAULT_BULLSAI_MODEL


def rewrite_model():
    """The helper model (follow-up rewrite, off-topic check)."""
    if provider() == "anthropic":
        return os.environ.get("REWRITE_MODEL") or "claude-haiku-4-5-20251001"
    return os.environ.get("BULLSAI_REWRITE_MODEL") or default_model()


def thinking_off():
    """BULLSAI_THINKING=off sends thinking disabled; anything else (default: "default") leaves the gateway's setting."""
    load_dotenv(ROOT / ".env")
    return (os.environ.get("BULLSAI_THINKING") or "default").strip().lower() == "off"


def make_client():
    load_dotenv(ROOT / ".env")
    if provider() == "anthropic":
        import anthropic                                  # only this optional path needs the package
        return anthropic.Anthropic()
    key, url = os.environ.get("BULLSAI_API_KEY"), os.environ.get("BULLSAI_BASE_URL")
    if not key or not url:
        raise LLMError("BULLSAI_API_KEY and BULLSAI_BASE_URL must be set in .env", fatal=True)
    from openai import OpenAI
    import httpx
    # connecting must fail fast (an unreachable gateway used to hold every call for 90 s, twice); a slow answer may still take up to 90 s
    return OpenAI(api_key=key, base_url=url, timeout=httpx.Timeout(90.0, connect=CONNECT_TIMEOUT), max_retries=1)


def _plain_error(exc):
    """A short, key-free description of a provider exception."""
    name, text = type(exc).__name__, str(exc)
    low = text.lower()
    if "401" in low or "authentication" in name.lower() or "invalid api key" in low or "incorrect api key" in low:
        return "the key was rejected (wrong or expired BULLSAI_API_KEY)", True
    if "404" in low or "notfound" in name.lower() or "model" in low and ("not found" in low or "does not exist" in low):
        return "the URL or model name was not found (check BULLSAI_BASE_URL / BULLSAI_MODEL)", True
    if "connection" in name.lower() or "timeout" in name.lower():
        return "could not reach the server (network or wrong BULLSAI_BASE_URL)", False
    if "credit balance" in low or "billing" in low:
        return "the Anthropic account has no credit left (check billing)", True
    if "budget" in low and "exceeded" in low:
        return "the budget of the course's BullsAI key is used up (HTTP 429: budget exceeded)", True
    if "429" in low or "ratelimit" in name.lower():
        return "rate limit reached, try again shortly", False
    return f"{name}: {text[:160]}", False


_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)
_FENCE = re.compile(r"^\s*```[a-zA-Z0-9]*\s*\n?(.*?)\n?\s*```\s*$", re.S)


def clean_text(text):
    """Drop <think> blocks (GLM and friends) and a code fence around the whole reply."""
    text = _THINK.sub("", text or "")
    if "</think>" in text:                                # an unopened block: keep what follows it
        text = text.split("</think>", 1)[1]
    text = text.strip()
    m = _FENCE.match(text)
    return (m.group(1) if m else text).strip()


def parse_json(text):
    """JSON from a model reply: fences/reasoning stripped; if prose surrounds one object, take the outermost braces."""
    text = clean_text(text)
    try:
        return json.loads(text)
    except ValueError:
        a, b = text.find("{"), text.rfind("}")
        if a == -1 or b <= a:
            raise
        return json.loads(text[a:b + 1])


def _schema_note(schema):
    return ("\n\nOUTPUT FORMAT: reply with ONE JSON object only, no code fences, no text before or after it, matching this "
            "JSON schema exactly (use every required field):\n" + json.dumps(schema))


def strict_schema(node):
    """A copy of a JSON schema with additionalProperties=false on every object (the Anthropic structured-output API requires it)."""
    if isinstance(node, dict):
        out = {k: strict_schema(v) for k, v in node.items()}
        if out.get("type") == "object" or "properties" in out:
            out["additionalProperties"] = False
        return out
    if isinstance(node, list):
        return [strict_schema(x) for x in node]
    return node


def complete(client, system, messages, max_tokens, model=None, schema=None):
    """One model call. `schema` (optional) asks for JSON: native structured output where the client supports it,
    otherwise the schema is added to the system prompt. Raises LLMError on any failure."""
    model = model or default_model()
    try:
        if hasattr(client, "messages"):                   # Anthropic-shaped client
            kw = dict(model=model, max_tokens=max_tokens, system=system, messages=messages)
            if schema is not None:
                kw["output_config"] = {"effort": "medium", "format": {"type": "json_schema", "schema": strict_schema(schema)}}
            resp = client.messages.create(**kw)
            if resp.stop_reason not in ("end_turn", "stop_sequence"):
                raise LLMError(f"model stopped with stop_reason={resp.stop_reason}")
            text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
            return LLMResult(text, resp.usage.input_tokens, resp.usage.output_tokens, getattr(resp, "model", model))
        sys_text = system + (_schema_note(schema) if schema is not None else "")
        extra = {"extra_body": {"thinking": {"type": "disabled"}}} if thinking_off() else {}
        effort = (os.environ.get("BULLSAI_REASONING_EFFORT") or "").strip().lower()      # off unless set (low|medium|high)
        if effort:
            extra["reasoning_effort"] = effort
        resp = client.chat.completions.create(
            model=model, max_tokens=max_tokens,
            messages=[{"role": "system", "content": sys_text}, *messages], **extra)
        choice = resp.choices[0]
        if choice.finish_reason == "length":
            if not clean_text(choice.message.content or ""):
                raise EmptyAnswer("model used its whole token limit without writing an answer")
            raise LLMError("model stopped with finish_reason=length (reply cut off)")
        if not clean_text(choice.message.content or ""):
            raise EmptyAnswer("model returned an empty reply")
        u = getattr(resp, "usage", None)
        return LLMResult(choice.message.content or "", getattr(u, "prompt_tokens", 0) or 0,
                         getattr(u, "completion_tokens", 0) or 0, getattr(resp, "model", None) or model)
    except LLMError:
        raise
    except Exception as exc:                              # provider errors: wrapped, key never included
        msg, fatal = _plain_error(exc)
        raise LLMError(msg, fatal=fatal) from None


def complete_json(client, system, messages, max_tokens, schema, model=None):
    """-> (data, usage). A reply that is not valid JSON is retried once; then LLMError (never a crash)."""
    total = {"input_tokens": 0, "output_tokens": 0}
    last, empty = None, False
    for _ in range(2):
        try:
            res = complete(client, system, messages, max_tokens, model, schema)
        except EmptyAnswer as exc:                        # an empty reply is retried once like a bad one
            last, empty = str(exc), True
            continue
        total["input_tokens"] += res.input_tokens
        total["output_tokens"] += res.output_tokens
        try:
            data = parse_json(res.text)
            if isinstance(data, dict):
                return data, total
            last = "not a JSON object"
        except ValueError as exc:
            last = str(exc)[:80]
        empty = False
    if empty:
        raise EmptyAnswer(last)
    raise LLMError(f"the model did not return valid JSON twice ({last})")


RERANK_MODEL = "BAAI/bge-reranker-v2-m3"


def rerank_enabled():
    """RERANK=on|off (default on)."""
    load_dotenv(ROOT / ".env")
    return (os.environ.get("RERANK") or "on").strip().lower() != "off"


def rerank(query, documents, timeout=3.0, model=None):
    """BullsAI POST {BULLSAI_BASE_URL}/rerank -> one relevance score per document, in the order given.
    Raises LLMError on any error, timeout or malformed reply (the caller falls back to the old order)."""
    import requests
    load_dotenv(ROOT / ".env")
    key, url = os.environ.get("BULLSAI_API_KEY"), os.environ.get("BULLSAI_BASE_URL")
    if not key or not url:
        raise LLMError("BULLSAI_API_KEY and BULLSAI_BASE_URL must be set in .env", fatal=True)
    try:
        r = requests.post(url.rstrip("/") + "/rerank", timeout=timeout, headers={"Authorization": f"Bearer {key}"},
                          json={"model": model or os.environ.get("BULLSAI_RERANK_MODEL") or RERANK_MODEL,
                                "query": query, "documents": list(documents)})
        r.raise_for_status()
        scores = [None] * len(documents)
        for item in r.json()["results"]:
            scores[item["index"]] = float(item["relevance_score"])
    except Exception as exc:
        raise LLMError(f"rerank failed ({type(exc).__name__})") from None
    if any(s is None for s in scores):
        raise LLMError("rerank returned too few scores")
    return scores


def price_of(model):
    return PRICES.get(model)


def cost_tracked(model):
    return model in PRICES


def cost_of(usage, model):
    """Dollars, or None when the model has no listed price (BullsAI)."""
    if not usage or model not in PRICES:
        return None
    p_in, p_out = PRICES[model]
    return (usage["input_tokens"] * p_in + usage["output_tokens"] * p_out) / 1e6


def probe(client, models, timeout=8.0):
    """One tiny, bounded request per model (no retry). -> [{"model", "ok", "seconds", "error"}]. A client that cannot be probed (a test double,
    the Anthropic-shaped client) counts as reachable: the real calls will report their own errors."""
    import time
    out = []
    if not hasattr(client, "with_options"):
        return [{"model": m, "ok": True, "seconds": 0.0, "error": ""} for m in models]
    quick = client.with_options(timeout=timeout, max_retries=0)
    for m in dict.fromkeys(models):
        t0 = time.perf_counter()
        try:
            if hasattr(quick, "messages"):                      # Anthropic-shaped client
                quick.messages.create(model=m, max_tokens=20, messages=[{"role": "user", "content": "Reply with the single word OK."}])
            else:
                quick.chat.completions.create(model=m, max_tokens=50, messages=[{"role": "user", "content": "Reply with the single word OK."}])
            out.append({"model": m, "ok": True, "seconds": round(time.perf_counter() - t0, 1), "error": ""})
        except Exception as exc:
            msg, _fatal = _plain_error(exc)
            out.append({"model": m, "ok": False, "seconds": round(time.perf_counter() - t0, 1), "error": msg})
    return out


# ---- the Quiz can run on its own backend (Claude) while Q&A and Guide stay on BullsAI -------------------------------------
QUIZ_DEFAULT_ANTHROPIC = ("claude-sonnet-5-5", "claude-opus-5-5")      # (writes and solves, independent verifier/auditor)


def quiz_backend(rt):
    """-> (client, generator model, verifier model, label). QUIZ_LLM_PROVIDER=anthropic uses the Anthropic API with QUIZ_GEN_MODEL (default
    claude-sonnet-5-5) and QUIZ_VERIFIER_MODEL (default claude-opus-5-5): two different models, so the independent check stays independent.
    Anything else keeps the runtime's BullsAI client and models. Keys are read from .env and never printed."""
    load_dotenv(ROOT / ".env")
    if (os.environ.get("QUIZ_LLM_PROVIDER") or "").strip().lower() == "anthropic":
        global _QUIZ_CLIENT
        if _QUIZ_CLIENT is None:
            import anthropic
            _QUIZ_CLIENT = anthropic.Anthropic(timeout=90.0, max_retries=1)
        gen = os.environ.get("QUIZ_GEN_MODEL") or QUIZ_DEFAULT_ANTHROPIC[0]
        ver = os.environ.get("QUIZ_VERIFIER_MODEL") or QUIZ_DEFAULT_ANTHROPIC[1]
        return _QUIZ_CLIENT, gen, ver, "Claude (Anthropic API)"
    from src.quiz import generate
    return rt.client, rt.model, generate.VERIFIER_MODEL, "BullsAI"


_QUIZ_CLIENT = None
