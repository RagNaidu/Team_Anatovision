"""Notes manager (instructor only; 403 for students through the router dependency). All the work is in src/notes_manager.py."""
from fastapi import APIRouter, Depends, File, Form, UploadFile

from app_api import catalog, convert, deps
from app_api.errors import ApiError
from app_api.schemas import (NoteAuditRow, NoteChange, NoteCreated, NoteDetail, NoteDiff, NoteEditIn, NoteList, NoteMappingIn, NotePublishIn, NotePurgeIn, NoteRollbackIn, NoteVersion, Ok)
from src import notes_manager as NM

router = APIRouter(prefix="/admin/notes", tags=["notes"], dependencies=[Depends(deps.instructor_ctx)])
MAX_READ = 61 << 20


def guarded(fn, *args, **kw):
    try:
        return fn(*args, **kw)
    except NM.ManagerError as exc:
        raise ApiError(exc.status, str(exc))


def when(ts):
    return convert.iso(ts) if ts else None


async def read_upload(file: UploadFile):
    data = await file.read(MAX_READ + 1)
    if len(data) > MAX_READ:
        raise ApiError(413, "That file is too large.")
    return file.filename or "", data


def fix_detail(d):
    d = dict(d)
    for k in ("created_at", "updated_at", "archived_at", "purge_after"):
        d[k] = when(d.get(k))
    live = {x["doc_id"]: x["title"] for x in NM.live_documents()}
    d["replaces_title"] = live.get(d.get("replaces") or "") or None
    d["has_pending"] = bool(d.get("job") and d["job"]["status"] in ("processing", "ready", "failed") and d.get("live_version"))
    d["editable"] = d["kind"] == "note" and d["status"] == "published"
    g = next((x for x in catalog.guides() if x["file"] == d.get("source_name")), None) if d["kind"] == "guide" and d["status"] == "published" else None
    d["guide_id"] = g["id"] if g else None
    d["regions"] = NM.list_documents()["regions"]
    d["lectures"] = sorted(x["title"] for x in NM.live_documents() if x["kind"] == "note")
    return d


@router.get("", response_model=NoteList)
def list_notes(kind: str = "", region: str = "", status: str = "", q: str = ""):
    out = guarded(NM.list_documents, kind=kind, region=region, status=status, q=q[:100])
    out["items"] = [{**r, "updated_at": when(r["updated_at"]) or ""} for r in out["items"]]
    return out


@router.post("", response_model=NoteCreated)
async def upload(file: UploadFile = File(...), kind: str = Form(""), replaces: str = Form(""), ctx=Depends(deps.instructor_ctx)):
    name, data = await read_upload(file)
    return guarded(NM.create_upload, ctx.log_user, name, data, kind=kind or None, replaces=replaces or None)


@router.get("/{doc_id}", response_model=NoteDetail)
def detail(doc_id: str):
    return fix_detail(guarded(NM.detail, doc_id))


@router.patch("/{doc_id}/mapping", response_model=Ok)
def mapping(doc_id: str, body: NoteMappingIn, ctx=Depends(deps.instructor_ctx)):
    guarded(NM.update_mapping, ctx.log_user, doc_id, region=body.region, replaces=body.replaces, lecture=body.lecture)
    return {"ok": True}


@router.post("/{doc_id}/replace", response_model=NoteCreated)
async def replace_file(doc_id: str, file: UploadFile = File(...), ctx=Depends(deps.instructor_ctx)):
    name, data = await read_upload(file)
    guarded(NM.ensure_managed_if_live, doc_id)
    return guarded(NM.create_upload, ctx.log_user, name, data, doc_id=doc_id)


@router.post("/{doc_id}/publish", response_model=NoteChange)
def publish(doc_id: str, body: NotePublishIn, ctx=Depends(deps.instructor_ctx)):
    return guarded(NM.publish, ctx.log_user, doc_id, access=body.access, students=body.students)


@router.post("/{doc_id}/discard", response_model=Ok)
def discard(doc_id: str, ctx=Depends(deps.instructor_ctx)):
    guarded(NM.discard, ctx.log_user, doc_id)
    return {"ok": True}


@router.put("/{doc_id}/sections", response_model=NoteChange)
def edit(doc_id: str, body: NoteEditIn, ctx=Depends(deps.instructor_ctx)):
    return guarded(NM.edit_sections, ctx.log_user, doc_id, [e.model_dump() for e in body.edits], body.note)


@router.get("/{doc_id}/versions", response_model=list[NoteVersion])
def versions(doc_id: str):
    return [{**v, "created_at": when(v["created_at"]) or ""} for v in guarded(NM.version_history, doc_id)]


@router.get("/{doc_id}/versions/{version}/diff", response_model=NoteDiff)
def version_diff(doc_id: str, version: int):
    d = guarded(NM.version_diff, doc_id, version)
    return {"against": f"version {d['against']}" if d["against"] else None, "counts": d["counts"], "rows": d["rows"]}


@router.post("/{doc_id}/rollback", response_model=NoteChange)
def rollback(doc_id: str, body: NoteRollbackIn, ctx=Depends(deps.instructor_ctx)):
    return guarded(NM.rollback, ctx.log_user, doc_id, body.version)


@router.post("/{doc_id}/archive", response_model=NoteChange)
def archive(doc_id: str, ctx=Depends(deps.instructor_ctx)):
    out = guarded(NM.archive, ctx.log_user, doc_id)
    return {"doc_id": doc_id, "restorable_until": when(out["restorable_until"])}


@router.post("/{doc_id}/restore", response_model=NoteChange)
def restore(doc_id: str, ctx=Depends(deps.instructor_ctx)):
    return guarded(NM.restore, ctx.log_user, doc_id)


@router.post("/{doc_id}/purge", response_model=Ok)
def purge(doc_id: str, body: NotePurgeIn, ctx=Depends(deps.instructor_ctx)):
    guarded(NM.purge, ctx.log_user, doc_id, body.confirm_title)
    return {"ok": True}


@router.get("/{doc_id}/audit", response_model=list[NoteAuditRow])
def audit(doc_id: str):
    return [{"at": when(a["ts"]), "user": a["user"], "action": a["action"], "detail": a["detail"]} for a in guarded(NM.audit_log, doc_id)]
