"""
로깅 설정 모듈 — 애플리케이션 전역 로깅 초기화

setup_logging()을 앱 시작 시 1회 호출하면:
  - 콘솔(stdout) 핸들러와 파일 로테이션 핸들러가 root 로거에 부착된다.
  - uvicorn 로거도 같은 핸들러로 통합되어 접근 로그까지 콘솔+파일 동시 누적된다.
  - 로그 파일은 log_dir 디렉토리 아래에 생성되며, 없으면 자동으로 만든다.
설정 값은 get_settings()에서 읽으며 CHOK_AI_ 접두어 환경 변수로 override 가능하다.
"""

import logging.config
import logging.handlers
import os

from app.core.config import get_settings


def setup_logging() -> None:
    """
    애플리케이션 전역 로깅을 초기화한다.

    - root 로거에 콘솔(StreamHandler)과 파일(RotatingFileHandler) 핸들러를 등록한다.
    - uvicorn / uvicorn.error / uvicorn.access 로거를 같은 핸들러로 통합하여
      uvicorn 접근 로그까지 콘솔과 파일에 동시 기록한다.
    - 로그 디렉토리(log_dir)가 존재하지 않으면 자동으로 생성한다.
    - disable_existing_loggers=False 로 기존 로거를 유지한다.
    """
    settings = get_settings()

    # 로그 디렉토리 자동 생성 — RotatingFileHandler 생성 전에 경로를 보장한다.
    os.makedirs(settings.log_dir, exist_ok=True)

    log_file_path = os.path.join(settings.log_dir, settings.log_file)

    # %(levelname)s 포함 — INFO / WARNING / ERROR 등 레벨 태그가 그대로 출력된다.
    _fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    _datefmt = "%Y-%m-%d %H:%M:%S"

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": _fmt,
                    "datefmt": _datefmt,
                },
            },
            "handlers": {
                # 콘솔 핸들러 — uvicorn 실행 시 터미널에 출력된다.
                "console": {
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout",
                    "formatter": "standard",
                },
                # 파일 핸들러 — 최대 log_max_bytes 단위로 로테이션, log_backup_count 개 보관.
                "file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "filename": log_file_path,
                    "maxBytes": settings.log_max_bytes,
                    "backupCount": settings.log_backup_count,
                    "encoding": "utf-8",
                    "formatter": "standard",
                },
            },
            "root": {
                # root 로거에 두 핸들러를 모두 부착한다.
                "level": settings.log_level.upper(),
                "handlers": ["console", "file"],
            },
            "loggers": {
                # uvicorn 로거 통합 — 접근 로그까지 콘솔+파일에 기록한다.
                # propagate=True 로 root 핸들러에 위임하고 별도 핸들러는 두지 않는다.
                "uvicorn": {
                    "level": settings.log_level.upper(),
                    "handlers": [],
                    "propagate": True,
                },
                "uvicorn.error": {
                    "level": settings.log_level.upper(),
                    "handlers": [],
                    "propagate": True,
                },
                "uvicorn.access": {
                    "level": settings.log_level.upper(),
                    "handlers": [],
                    "propagate": True,
                },
            },
        }
    )
