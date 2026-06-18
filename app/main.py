from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.errors import handle_unexpected
from app.middleware import add_process_time

settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    description=settings.app_description,
    version=settings.app_version,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_methods,
    allow_headers=settings.cors_headers,
    expose_headers=settings.cors_exposed_headers,
    max_age=settings.cors_max_age,
)
app.middleware("http")(add_process_time)
app.add_exception_handler(Exception, handle_unexpected)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}
