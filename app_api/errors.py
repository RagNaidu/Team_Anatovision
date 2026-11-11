"""Every non-2xx response is {"error": "<a message fit to show the user>"}: no stack traces, no framework detail."""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("anatovision.api")


class ApiError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


def respond(status, message):
    return JSONResponse({"error": message}, status_code=status)


GENERIC = {400: "That request could not be understood.", 401: "Please sign in.", 403: "You do not have access to that.",
           404: "That was not found.", 405: "That method is not allowed here.", 409: "That cannot be done right now.",
           422: "Something in the request is not valid.", 429: "Too many attempts. Try again in a few minutes."}


def validation_message(exc):
    """The first problem, in plain words (field names only, never the submitted value)."""
    errors = exc.errors()
    if not errors:
        return GENERIC[422]
    e = errors[0]
    field = ".".join(str(x) for x in e.get("loc", ()) if x not in ("body", "query", "path"))
    kind = e.get("type", "")
    if kind == "missing":
        return f"“{field}” is required."
    if kind.startswith("string_too_long") or kind.startswith("too_long"):
        return f"“{field}” is too long."
    if kind.startswith("literal_error") or kind.startswith("enum"):
        return f"“{field}” has a value that is not allowed."
    return f"“{field}” is not valid." if field else GENERIC[422]


def install(app: FastAPI):
    @app.exception_handler(ApiError)
    async def _api(_: Request, exc: ApiError):
        return respond(exc.status, exc.message)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        return respond(exc.status_code, exc.detail if isinstance(exc.detail, str) and exc.status_code not in (404, 405) else
                       GENERIC.get(exc.status_code, "Something went wrong."))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        return respond(422, validation_message(exc))

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception):
        log.exception("unhandled error")
        return respond(500, "Something went wrong on our side. Please try again.")
