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
    from src import guide_marks
    monkeypatch.setattr(guide_marks, "DB_PATH", tmp_path / "default_marks.db")
    from src.qbank import store as qbank_db
    monkeypatch.setattr(qbank_db, "DB_PATH", tmp_path / "default_bank" / "bank.db")
    monkeypatch.setenv("QUIZ_LLM_PROVIDER", "bullsai")   # tests never build the real Claude client
    monkeypatch.setenv("RERANK", "off")          # no test calls the reranker unless it enables it with a mock
    monkeypatch.setenv("WEB_FALLBACK", "off")    # no test touches the network unless it turns the web on AND fakes the lookup
    monkeypatch.setenv("WEB_ALLOW_WIKIPEDIA", "off")
    monkeypatch.setenv("TAVILY_API_KEY", "")


def pytest_sessionstart(session):
    """REVISION_STAGE=data/staging_v2 pytest ...: run the whole suite against the staged revised data (sections, guides, map, index, fact-check report)."""
    import os
    stage = os.environ.get("REVISION_STAGE")
    if stage:
        from pathlib import Path
        from src.ingest import stage as ST
        cm = ST.use(Path(stage).resolve())
        cm.__enter__()
        session.config._revision_stage = cm


def pytest_sessionfinish(session, exitstatus):
    cm = getattr(session.config, "_revision_stage", None)
    if cm is not None:
        cm.__exit__(None, None, None)
