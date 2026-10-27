"""One short question to the configured model. Prints the answer, token counts and model name (never the key)."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import llm  # noqa: E402


def main():
    try:
        client = llm.make_client()
        model = llm.default_model()
        t0 = time.perf_counter()
        res = llm.complete(client, "You are a concise anatomy tutor.",
                           [{"role": "user", "content": "In one sentence: what is the femoral triangle?"}], 800, model)
    except llm.LLMError as exc:
        print(f"FAILED: {exc}")
        return 1
    print(f"provider: {llm.provider()}\nmodel: {res.model or model}\nseconds: {time.perf_counter() - t0:.1f}")
    print(f"tokens: in {res.input_tokens} / out {res.output_tokens}\nraw reply: {res.text[:400]!r}\ncleaned: {llm.clean_text(res.text)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
