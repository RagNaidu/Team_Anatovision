"""Shared test setup: no test may write to the real question log, settings or flags (they hold real student data)."""
import pytest


@pytest.fixture(autouse=True)
def _never_touch_real_runtime_files(tmp_path, monkeypatch):
    from src import chat_store, guide_store, usage, web_fallback
    from src.quiz import store as quiz_store
    from src.modes import qa
    monkeypatch.setattr(usage, "QUESTION_LOG_PATH", tmp_path / "default_question_log.jsonl")
    monkeypatch.setattr(usage, "SETTINGS_PATH", tmp_path / "default_settings.json")
    monkeypatch.setattr(qa, "FLAGS_PATH", tmp_path / "default_flags.jsonl")
    monkeypatch.setattr(web_fallback, "CACHE_DIR", tmp_path / "default_web_cache")
    monkeypatch.setattr(chat_store, "DB_PATH", tmp_path / "default_chats.db")
    monkeypatch.setattr(guide_store, "DB_PATH", tmp_path / "default_guide_sessions.db")
    monkeypatch.setattr(quiz_store, "DB_PATH", tmp_path / "default_quizzes.db")
    monkeypatch.setenv("QUIZ_LLM_PROVIDER", "bullsai")   # tests never build the real Claude client
    monkeypatch.setenv("RERANK", "off")          # no test calls the reranker unless it enables it with a mock
    monkeypatch.setenv("WEB_FALLBACK", "off")    # no test touches the network unless it turns the web on AND fakes the lookup
    monkeypatch.setenv("WEB_ALLOW_WIKIPEDIA", "off")
    monkeypatch.setenv("TAVILY_API_KEY", "")
