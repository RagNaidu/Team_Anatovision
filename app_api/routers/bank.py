"""Question bank (instructor only; 403 for students through the router dependency). The logic is in src/qbank/. Students never read from here: their quizzes pick
approved + practice questions through src/qbank/integrate.py."""
from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import Response

from app_api import convert, deps
from app_api.errors import ApiError
from app_api.schemas import (BankBulkIn, BankBulkOut, BankCommentIn, BankDetail, BankDismissIn, BankImportIn, BankImportOut, BankImportPreview, BankList, BankRestoreIn, BankSaveIn, Ok)
from src.qbank import importer, integrate, service
from src.qbank import store as S

router = APIRouter(prefix="/admin/bank", tags=["bank"], dependencies=[Depends(deps.instructor_ctx)])
FILTERS = ("status", "use", "source", "region", "difficulty", "lecture", "tag", "q")


def guarded(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except S.BankError as exc:
        raise ApiError(exc.status, str(exc))


def bank():
    return S.BankStore()


def filters(status="", use="", source="", region="", difficulty="", lecture="", tag="", q="", flagged=False):
    return {"status": status, "use": use, "source": source, "region": region, "difficulty": difficulty, "lecture": lecture, "tag": tag, "q": q[:200], "flagged": flagged}


def stamp(d):
    d = dict(d)
    d["updated_at"] = convert.iso(d["updated_at"])
    return d


def rt_if_loaded(request):
    return getattr(request.app.state, "runtime", None)


@router.get("", response_model=BankList)
def list_bank(status: str = "", use: str = "", source: str = "", region: str = "", difficulty: str = "", lecture: str = "", tag: str = "", q: str = "", flagged: bool = False, page: int = Query(1, ge=1)):
    out = guarded(service.listing, bank(), filters(status, use, source, region, difficulty, lecture, tag, q, flagged), page)
    out["items"] = [stamp(r) for r in out["items"]]
    return out


@router.get("/export.csv")
def export(status: str = "", use: str = "", source: str = "", region: str = "", difficulty: str = "", lecture: str = "", tag: str = "", q: str = "", flagged: bool = False):
    rows = service.filtered(bank(), filters(status, use, source, region, difficulty, lecture, tag, q, flagged))
    return Response(S.export_csv(rows), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="question-bank.csv"'})


@router.get("/template.csv")
def template_csv():
    return Response(importer.template_csv(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="question-template.csv"'})


@router.get("/template.xlsx")
def template_xlsx():
    return Response(importer.template_xlsx(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="question-template.xlsx"'})


@router.post("/import/preview", response_model=BankImportPreview)
async def import_preview(file: UploadFile = File(None), import_id: str = Form(""), mapping: str = Form("")):
    import json
    try:
        m = json.loads(mapping) if mapping else None
    except ValueError:
        raise ApiError(422, "The mapping was not understood.")
    data = await file.read(importer.MAX_BYTES + 1) if file is not None else b""
    return guarded(service.preview_import, bank(), (file.filename if file else "") or "", data, m, import_id or None)


@router.post("/import/commit", response_model=BankImportOut)
def import_commit(body: BankImportIn, request: Request, ctx=Depends(deps.instructor_ctx)):
    return guarded(service.commit_import, bank(), body.import_id, body.mapping, body.status, body.use, body.skip_duplicates, ctx.log_user, rt_if_loaded(request))


@router.post("/bulk", response_model=BankBulkOut)
def bulk(body: BankBulkIn, request: Request, ctx=Depends(deps.instructor_ctx)):
    b, a, v = bank(), body.action, body.value
    if a == "run_checks":
        rt = deps.runtime(request)
        for qid in body.ids[:50]:
            service.run_ai_checks(b, qid, rt)
        return {"changed": min(len(body.ids), 50)}
    if a in ("approve", "retire", "draft"):
        n = guarded(b.bulk, body.ids, {"status": {"approve": "approved", "retire": "retired", "draft": "draft"}[a]}, by=ctx.log_user, note=f"bulk: {a}")
    elif a == "set_use":
        n = guarded(b.bulk, body.ids, {"use": v}, by=ctx.log_user, note=f"bulk: use = {v}")
    else:
        if not v.strip():
            raise ApiError(422, "Type a tag first.")
        n = guarded(b.bulk, body.ids, add_tags=[v] if a == "add_tag" else (), remove_tags=[v] if a == "remove_tag" else (), by=ctx.log_user, note=f"bulk: {a} {v}")
    return {"changed": n}


@router.post("", response_model=BankDetail)
def create(body: BankSaveIn, ctx=Depends(deps.instructor_ctx)):
    d = body.model_dump()
    note = d.pop("note")
    q = guarded(service.create_with_checks, bank(), d, ctx.log_user, note or "created")
    return fix(guarded(service.detail, bank(), q["id"]))


def fix(d):
    d = dict(d)
    d["created_at"], d["updated_at"] = convert.iso(d["created_at"]), convert.iso(d["updated_at"])
    d["comments"] = [{**c, "at": convert.iso(c["at"])} for c in d["comments"]]
    d["versions"] = [{**v, "at": convert.iso(v["at"])} for v in d["versions"]]
    return d


@router.get("/{qid}", response_model=BankDetail)
def get(qid: str):
    return fix(guarded(service.detail, bank(), qid))


@router.put("/{qid}", response_model=BankDetail)
def edit(qid: str, body: BankSaveIn, ctx=Depends(deps.instructor_ctx)):
    d = body.model_dump()
    note = d.pop("note")
    b = bank()
    q = guarded(b.get, qid)
    if q is None:
        raise ApiError(404, "That question was not found.")
    keep = {k: q["data"][k] for k in ("links", "sample")}
    guarded(b.update, qid, {**d, **keep}, ctx.log_user, note)
    guarded(service.run_local_checks, b, qid)
    return fix(guarded(service.detail, b, qid))


@router.post("/{qid}/restore", response_model=BankDetail)
def restore(qid: str, body: BankRestoreIn, ctx=Depends(deps.instructor_ctx)):
    b = bank()
    guarded(b.restore, qid, body.version, ctx.log_user)
    guarded(service.run_local_checks, b, qid)
    return fix(guarded(service.detail, b, qid))


@router.post("/{qid}/comments", response_model=BankDetail)
def comment(qid: str, body: BankCommentIn, ctx=Depends(deps.instructor_ctx)):
    guarded(bank().add_comment, qid, ctx.log_user, body.text)
    return fix(guarded(service.detail, bank(), qid))


@router.post("/{qid}/check", response_model=BankDetail)
def check(qid: str, request: Request):
    b = bank()
    if b.get(qid) is None:
        raise ApiError(404, "That question was not found.")
    guarded(service.run_ai_checks, b, qid, deps.runtime(request))
    return fix(guarded(service.detail, b, qid))


@router.post("/{qid}/flags/dismiss", response_model=BankDetail)
def dismiss(qid: str, body: BankDismissIn):
    b = bank()
    guarded(b.dismiss_flag, qid, body.kind, body.code, body.dismissed)
    return fix(guarded(service.detail, b, qid))


@router.post("/{qid}/recheck", response_model=BankDetail)
def recheck_done(qid: str, ctx=Depends(deps.instructor_ctx)):
    """The instructor looked at the question again after the notes changed: refresh its links and clear the mark."""
    from pathlib import Path
    from src import notes_manager as NM
    b = bank()
    if b.get(qid) is None:
        raise ApiError(404, "That question was not found.")
    chunks = NM._read_jsonl(Path(NM.live()["index"]) / "chunks.jsonl")
    integrate.clear_recheck(qid, chunks, b, ctx.log_user)
    return fix(guarded(service.detail, b, qid))
