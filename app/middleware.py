import time

from fastapi import Request
from starlette.middleware.base import RequestResponseEndpoint


async def add_process_time(request: Request, call_next: RequestResponseEndpoint):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start
    response.headers["X-Process-Time"] = f"{elapsed:.4f}"
    return response
