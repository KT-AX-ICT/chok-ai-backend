"""
CHOK AI Backend — FastAPI 게이트웨이
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import router
from app.core.config import get_settings
from app.core.errors import handle_unexpected

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description=settings.app_description,
    version=settings.app_version,
    docs_url="/docs",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=settings.cors_methods,
    allow_headers=settings.cors_headers,
    expose_headers=settings.cors_exposed_headers,
    allow_credentials=settings.cors_allow_credentials,
    max_age=settings.cors_max_age,
)

# 전역 예외 핸들러 (core 위임)
app.add_exception_handler(Exception, handle_unexpected)

# 라우터 등록
app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok"}
