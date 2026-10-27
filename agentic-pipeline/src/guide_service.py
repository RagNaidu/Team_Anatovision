"""The seam between the Guide screen and the conversation engine: which guides a user may open, opening or restoring that guide's own
session, taking a turn, and saving it. No Streamlit here, so the rules are tested directly.

  guides_for(allowed)                 the guide entries a user may open (src.ingest.guides.accessible_guides; None = instructor)
  open_session(username, file, allowed, ...) -> Session | None   None when the guide is not one the user may open (checked here)
  Session.turn(text=None, action=None) -> Reply     runs the engine; the session state is replaced ONLY when the reply is ok
  Session.reset()                     the explicit "start over": a fresh state, the saved one deleted
Saved sessions are per user and per guide (src/guide_store.py); a professor previewing as a student passes persist=False.
"""
from dataclasses import dataclass, field
from functools import lru_cache

from src import guide_store
from src.ingest import guides as G
from src.modes import guide_chat as C
from src.modes import guide_slides as GS


@lru_cache(maxsize=64)
def _steps(file, class_label, stamp):
    return tuple(C.build_steps(GS.slides_of(file), class_label))


def steps_of(entry):
    p = G.SLIDES_PATH
    return list(_steps(entry["file"], entry["class_label"], p.stat().st_mtime if p.exists() else 0))


def guides_for(allowed):
    return G.accessible_guides(allowed)


@dataclass
class Session:
    username: str
    entry: dict
    steps: list
    state: dict
    persist: bool = True
    chat: C.GuideChat = None
    store: object = None
    last_error: str = ""

    def view(self):
        return C.view(self.state, self.steps)

    def turn(self, text=None, action=None):
        reply = self.chat.handle(self.state, text=text, action=action)
        if reply.ok:
            self.state, self.last_error = reply.state, ""
            self.save()
        else:
            self.last_error = reply.error                 # self.state is untouched: the last valid position stays
        return reply

    def save(self):
        if self.persist:
            self.store.save(self.username, self.entry["file"], self.state)

    def reset(self):
        self.state = C.new_state(self.entry, self.state.get("body_type", ""))
        self.last_error = ""
        if self.persist:
            self.store.delete(self.username, self.entry["file"])


def open_session(username, file, allowed, client=None, model="", body_type="", persist=True, store=None, interpret=None, write=None):
    entry = next((e for e in guides_for(allowed) if e["file"] == file), None)
    if entry is None:
        return None
    steps = steps_of(entry)
    store = store or guide_store.GuideStore()
    stored = store.load(username, file) if persist else None
    state = C.restore(stored, entry, steps, body_type)
    if body_type:
        state["body_type"] = body_type
    chat = C.GuideChat(entry, steps, client, model, interpret=interpret, write=write)
    return Session(username, entry, steps, state, persist, chat, store)
