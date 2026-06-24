"""
Tool① 이벤트 템플릿 분류 — 로그 content → event_id (규칙 기반)

BGL 이벤트 템플릿(`<*>`=가변 토큰)에 로그 본문을 매칭해 event_id를 산출한다.

[템플릿 출처 — 우선순위]
1. app/data/event_templates.json (bgl_template 전체 카탈로그) — 있으면 우선
2. (폴백) clusters.json에 임베드된 클러스터별 템플릿 부분집합

전체 카탈로그(event_templates.json) 수령 전까지는 2번 폴백으로 동작한다.
형식은 ERD bgl_template 기준: [{"event_id": "E1", "event_template": "..."}].
매칭 실패 시 None → 응답 eventId는 null(규정)이고, Tool③에서 미분류(99) 버킷으로 흐른다.
"""

import json
import logging
import re
from functools import lru_cache
from pathlib import Path

from app.data.patterns import load_clusters

logger = logging.getLogger(__name__)

# Tool① 전용 카탈로그(있으면 우선). 없으면 clusters.json 임베드 템플릿으로 폴백.
_CATALOG_PATH = Path(__file__).resolve().parent / "event_templates.json"

# 가변 토큰 표기
_WILDCARD = "<*>"


def _template_to_regex(template: str) -> re.Pattern[str]:
    """BGL 템플릿(<*>=가변)을 정규식으로. 리터럴은 escape, <*>는 비탐욕 토큰(.+?)."""
    parts = template.split(_WILDCARD)
    pattern = ".+?".join(re.escape(p) for p in parts)
    return re.compile(pattern)


def _catalog() -> list[tuple[str, str]]:
    """(event_id, template) 목록. 전용 카탈로그 우선, 없으면 clusters.json 폴백."""
    if _CATALOG_PATH.exists():
        raw = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
        return [(e["event_id"], e["event_template"]) for e in raw]
    pairs: list[tuple[str, str]] = []
    for cluster in load_clusters():
        for entry in cluster.event_template:
            pairs.append((entry.event_id, entry.template))
    return pairs


@lru_cache
def _compiled() -> list[tuple[str, re.Pattern[str]]]:
    """컴파일된 (event_id, regex). 리터럴이 긴(=구체적) 템플릿을 우선 매칭하도록 정렬."""
    items = _catalog()
    items.sort(key=lambda t: len(t[1].replace(_WILDCARD, "")), reverse=True)
    return [(event_id, _template_to_regex(template)) for event_id, template in items]


def match_event_template(content: str) -> str | None:
    """로그 content를 이벤트 템플릿에 매칭해 event_id 반환. 미일치 시 None."""
    for event_id, regex in _compiled():
        if regex.search(content):
            return event_id
    return None
