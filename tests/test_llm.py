"""The model adapter: no real API call anywhere (the OpenAI-style client is a fake)."""
from types import SimpleNamespace

import pytest

from src import llm, query

SCHEMA = {"type": "object", "properties": {"a": {"type": "integer"}}, "required": ["a"]}


class FakeOpenAI:
    def __init__(self, *replies, finish="stop", exc=None):
        self.replies, self.calls, self.finish, self.exc = list(replies), [], finish, exc
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.calls.append(kw)
        if self.exc:
            raise self.exc
        text = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        msg = SimpleNamespace(content=text, reasoning_content="long hidden thoughts")
        return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason=self.finish)], model="glm-x",
                               usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7))


def test_complete_sends_system_message_and_counts_tokens():
    c = FakeOpenAI("hello")
    r = llm.complete(c, "SYS", [{"role": "user", "content": "q"}], 50, "m1")
    assert (r.text, r.input_tokens, r.output_tokens, r.model) == ("hello", 11, 7, "glm-x")
    sent = c.calls[0]
    assert sent["model"] == "m1" and sent["max_tokens"] == 50
    assert sent["messages"][0] == {"role": "system", "content": "SYS"} and sent["messages"][1]["content"] == "q"


def test_schema_goes_into_the_system_prompt():
    c = FakeOpenAI('{"a": 1}')
    llm.complete(c, "SYS", [{"role": "user", "content": "q"}], 50, "m", SCHEMA)
    assert "JSON schema" in c.calls[0]["messages"][0]["content"] and '"required"' in c.calls[0]["messages"][0]["content"]


@pytest.mark.parametrize("raw", ['{"a": 1}', '```json\n{"a": 1}\n```', '<think>hmm {"a": 2}</think>\n{"a": 1}',
                                 'Here you go:\n{"a": 1}\nDone.', '```\n{"a": 1}\n```  '])
def test_json_is_cleaned(raw):
    data, usage = llm.complete_json(FakeOpenAI(raw), "S", [{"role": "user", "content": "q"}], 50, SCHEMA, "m")
    assert data == {"a": 1} and usage == {"input_tokens": 11, "output_tokens": 7}


def test_bad_json_is_retried_once_and_tokens_are_summed():
    c = FakeOpenAI("not json at all", '{"a": 1}')
    data, usage = llm.complete_json(c, "S", [{"role": "user", "content": "q"}], 50, SCHEMA, "m")
    assert data == {"a": 1} and len(c.calls) == 2 and usage["input_tokens"] == 22


def test_two_bad_replies_fail_with_a_clear_error_not_a_crash():
    c = FakeOpenAI("nope")
    with pytest.raises(llm.LLMError, match="valid JSON twice"):
        llm.complete_json(c, "S", [{"role": "user", "content": "q"}], 50, SCHEMA, "m")
    assert len(c.calls) == 2


def test_cut_off_reply_is_an_error():
    with pytest.raises(llm.LLMError, match="length"):
        llm.complete(FakeOpenAI("x", finish="length"), "S", [], 5, "m")


def test_provider_errors_are_wrapped_and_never_carry_the_key():
    class AuthenticationError(Exception):
        pass
    with pytest.raises(llm.LLMError) as e:
        llm.complete(FakeOpenAI("x", exc=AuthenticationError("401 invalid api key sk-SECRET")), "S", [], 5, "m")
    assert e.value.fatal and "SECRET" not in str(e.value) and "BULLSAI_API_KEY" in str(e.value)


def test_defaults_need_no_anthropic_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setattr(llm, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("BULLSAI_MODEL", "glm")
    monkeypatch.delenv("BULLSAI_REWRITE_MODEL", raising=False)
    assert llm.provider() == "bullsai" and llm.default_model() == "glm" and llm.rewrite_model() == "glm"
    monkeypatch.setenv("BULLSAI_REWRITE_MODEL", "small")
    assert llm.rewrite_model() == "small"
    monkeypatch.setenv("BULLSAI_API_KEY", "k")
    monkeypatch.setenv("BULLSAI_BASE_URL", "http://localhost:1/v1")
    assert llm.make_client().chat.completions


def test_cost_is_not_tracked_for_bullsai_models_but_is_for_listed_ones():
    u = {"input_tokens": 1_000_000, "output_tokens": 1_000_000}
    assert llm.cost_of(u, "zai-org/GLM-5.3-Flash") is None and not llm.cost_tracked("zai-org/GLM-5.3-Flash")
    assert llm.cost_of(u, "claude-sonnet-5-5") == 12.0


def test_helper_calls_strip_reasoning():
    c = FakeOpenAI("<think>the student means the femoral triangle</think>femoral triangle apex")
    q, usage, how = query.rewrite_query(c, "What is its apex?", [{"question": "femoral triangle?", "answer": "a"}], "m")
    assert q == "femoral triangle apex" and how == "rewritten" and usage["output_tokens"] == 7
    ok, _ = query.is_anatomy_question(FakeOpenAI("<think>x</think>NO"), "pizza?", "m")
    assert ok is False


# ---- empty answers -------------------------------------------------------------------------------------------------

def test_an_empty_reply_is_retried_once_then_reported_as_empty():
    c = FakeOpenAI("   ")
    import pytest
    with pytest.raises(llm.EmptyAnswer):
        llm.complete_json(c, "S", [{"role": "user", "content": "q"}], 50, SCHEMA, "m")
    assert len(c.calls) == 2


def test_an_empty_first_reply_then_a_good_one_succeeds():
    data, _ = llm.complete_json(FakeOpenAI("", '{"a": 1}'), "S", [{"role": "user", "content": "q"}], 50, SCHEMA, "m")
    assert data == {"a": 1}


def test_reasoning_that_uses_up_the_limit_is_an_empty_answer_not_a_cut_off_one():
    import pytest
    with pytest.raises(llm.EmptyAnswer):
        llm.complete(FakeOpenAI("", finish="length"), "S", [], 5, "m")


def test_the_student_sees_a_clear_message_when_the_model_returns_no_answer():
    from tests.test_service import chunk, EMPTY
    from src import service
    from src.student_view import build
    rt = service.Runtime(searcher=__import__("tests.test_service", fromlist=["x"]).FakeSearcher([chunk()]), next_of={},
                         client=FakeOpenAI(""), model="m")
    res = service.ask("walls?", "", True, None, runtime=rt, ctx=EMPTY)
    assert res["status"] == "error" and res["answer_text"] == llm.EMPTY_MESSAGE
    view = build(res)
    assert llm.EMPTY_MESSAGE in str(view) and view["answer_text"].strip()
