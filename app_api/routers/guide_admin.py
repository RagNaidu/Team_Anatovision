"""Guide image annotations (instructor only; 403 for students through the router dependency): a guide's stations with their images and ALL marks (drafts included),
add / edit / delete / reorder marks, and approve or un-approve a station's marks. Students only ever receive approved marks (routers/guide.py)."""
from fastapi import APIRouter, Depends

from app_api import catalog, deps, guide_media
from app_api.errors import ApiError
from app_api.routers.guide import stations_of
from app_api.schemas import AdminMark, AnnGuide, ApproveIn, Changed, CropReviewIn, MarkIn, MarkOrderIn, MarkPatch, Ok
from src import guide_images as GI
from src import guide_marks as GM

router = APIRouter(prefix="/admin/guides", tags=["guide-annotations"], dependencies=[Depends(deps.instructor_ctx)])


def need(guide_id):
    g = catalog.guide_by_id(guide_id)
    if g is None:
        raise ApiError(404, "That guide was not found.")
    return g


def guarded(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except GM.MarkError as exc:
        raise ApiError(exc.status, str(exc))


def station_of_slide(g, slide):
    return next((s for s in stations_of(g) if slide in s["slides"]), None)


@router.get("/{guide_id}/annotations", response_model=AnnGuide)
def annotations(guide_id: str):
    g = need(guide_id)
    store = GM.MarkStore()
    marks = store.list(g["id"])
    out = []
    for s in stations_of(g):
        imgs = guide_media.station_images(g, s, marks=[m for m in marks if m["slide"] in s["slides"]], student=False, store=store)
        mine = [m for m in marks if (m["slide"], m["crop"]) in {(i["slide"], i["crop"]) for i in imgs}]
        out.append({"index": s["n"] - 1, "title": s["title"], "steps": list(s["steps"]), "slides": list(s["slides"]), "image_only": s["image_only"], "images": imgs,
                    "drafts": sum(m["status"] == "draft" for m in mine), "approved": sum(m["status"] == "approved" for m in mine)})
    return {"guide_id": g["id"], "title": g["title"], "stations": out, "rendered": GI.meta(g["id"])["mode"] in ("render", "pictures")}


@router.post("/{guide_id}/marks", response_model=AdminMark)
def add_mark(guide_id: str, body: MarkIn, ctx=Depends(deps.instructor_ctx)):
    g = need(guide_id)
    st = station_of_slide(g, body.slide)
    if st is None or not GI.has_image(g["id"], body.slide, body.crop):
        raise ApiError(422, "That picture does not exist.")
    if body.step is not None and body.step >= len(st["steps"]):
        raise ApiError(422, "That step does not exist in this station.")
    return guide_media.admin_mark(guarded(GM.MarkStore().create, g["id"], body.slide, body.kind, body.geom, body.text, body.step, ctx.log_user, crop=body.crop))


def own(g, mark_id):
    m = GM.MarkStore().get(mark_id)
    if m is None or m["guide_id"] != g["id"]:
        raise ApiError(404, "That mark was not found.")
    return m


@router.put("/{guide_id}/marks/{mark_id}", response_model=AdminMark)
def edit_mark(guide_id: str, mark_id: str, body: MarkPatch, ctx=Depends(deps.instructor_ctx)):
    g = need(guide_id)
    m = own(g, mark_id)
    patch = body.model_dump(exclude_unset=True)
    if patch.get("step") is not None:
        st = station_of_slide(g, m["slide"])
        if st is None or patch["step"] >= len(st["steps"]):
            raise ApiError(422, "That step does not exist in this station.")
    return guide_media.admin_mark(guarded(GM.MarkStore().update, mark_id, patch, ctx.log_user))


@router.delete("/{guide_id}/marks/{mark_id}", response_model=Ok)
def delete_mark(guide_id: str, mark_id: str, ctx=Depends(deps.instructor_ctx)):
    g = need(guide_id)
    own(g, mark_id)
    guarded(GM.MarkStore().delete, mark_id, ctx.log_user)
    return {"ok": True}


@router.post("/{guide_id}/marks/reorder", response_model=Ok)
def reorder(guide_id: str, body: MarkOrderIn):
    g = need(guide_id)
    guarded(GM.MarkStore().reorder, g["id"], body.slide, body.ids, body.crop)
    return {"ok": True}


@router.post("/{guide_id}/stations/{index}/approve", response_model=Changed)
def approve_station(guide_id: str, index: int, body: ApproveIn, ctx=Depends(deps.instructor_ctx)):
    g = need(guide_id)
    stations = stations_of(g)
    if not 0 <= index < len(stations):
        raise ApiError(404, "That station was not found.")
    n = guarded(GM.MarkStore().set_status, g["id"], stations[index]["slides"], "approved" if body.approve else "draft", ctx.log_user)
    return {"changed": n}


@router.post("/{guide_id}/slides/{slide}/crops/{crop}/review", response_model=Ok)
def review_crop(guide_id: str, slide: int, crop: int, body: CropReviewIn, ctx=Depends(deps.instructor_ctx)):
    """The instructor looked at a cropped picture. A low-confidence crop reaches students only after this."""
    g = need(guide_id)
    if not GI.has_image(g["id"], slide, crop):
        raise ApiError(404, "That picture does not exist.")
    GM.MarkStore().set_reviewed(g["id"], slide, crop, body.ok, ctx.log_user)
    return {"ok": True}
