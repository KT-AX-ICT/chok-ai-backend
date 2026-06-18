import logging

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unexpected error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal",
            "message": "Unexpected server error.",
            "path": request.url.path,
        },
    )
