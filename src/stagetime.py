"""Stage timing and progress phases for one question. Off (a no-op) unless a Recorder is installed for the current request.

    rec = stagetime.Recorder(on_phase=callback)
    with stagetime.use(rec):
        service.ask(...)            # the stages record themselves: rewrite, term_check, search, rerank, coverage_check, web_lookup, answer, ...
    rec.rows                        # [{"name", "start", "seconds"}], start = seconds since the recorder was made (overlaps show parallel work)

A stage may name a `phase` ("searching" | "reading" | "writing" | "checking"): the recorder passes it to on_phase when the stage starts. Only these
four words ever leave the server as progress; no text of an answer does. Threads started for parallel work must run inside
`stagetime.in_context(fn)` so they report to the same recorder.
"""
import contextvars
import threading
import time
from contextlib import contextmanager

_current = contextvars.ContextVar("stage_recorder", default=None)
PHASES = ("searching", "reading", "writing", "checking")


class Recorder:
    def __init__(self, on_phase=None):
        self.t0, self.rows, self.on_phase, self.lock = time.perf_counter(), [], on_phase, threading.Lock()

    def add(self, name, start, seconds):
        with self.lock:
            self.rows.append({"name": name, "start": round(start - self.t0, 3), "seconds": round(seconds, 3)})

    def seconds(self, name):
        return round(sum(r["seconds"] for r in self.rows if r["name"] == name), 3)


@contextmanager
def use(rec):
    token = _current.set(rec)
    try:
        yield rec
    finally:
        _current.reset(token)


@contextmanager
def stage(name, phase=None):
    rec = _current.get()
    if rec is None:
        yield
        return
    if phase and rec.on_phase:
        rec.on_phase(phase)
    t = time.perf_counter()
    try:
        yield
    finally:
        rec.add(name, t, time.perf_counter() - t)


def in_context(fn):
    """fn wrapped to run in a copy of the current context (for a worker thread)."""
    ctx = contextvars.copy_context()
    return lambda *a, **k: ctx.run(fn, *a, **k)
