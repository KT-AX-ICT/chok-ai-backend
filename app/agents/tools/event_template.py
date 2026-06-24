"""Tool ① 이벤트 템플릿 분류 (drain template-match).

raw 로그 ``content`` 를 BGL 정식 ``eventId`` 로 매핑한다.
매칭 규칙은 ``metadata/event_template.json`` 의 ``match_guide`` 를 따른다.

- regex 는 ``^...$`` 앵커, ``<*>`` 는 ``(.*?)`` 비탐욕 매칭.
- 여러 템플릿이 매칭되면 ``literal_len`` 이 큰(가장 구체적인) 쪽을 선택.
- 매칭 0건이면 ``unknown`` 처리.

LangGraph 등 오케스트레이션 프레임워크에 의존하지 않는 순수 함수로 작성한다.
"""

import json
import re
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

METADATA_PATH = Path(__file__).parent / "metadata" / "event_template.json"

UNKNOWN_EVENT_ID = "unknown"


class EventTemplateResult(BaseModel):
    """이벤트 템플릿 판정 결과 (내부 Tool 결과 모델)."""

    event_id: str = Field(
        description="매칭된 BGL 이벤트 ID(예: 'E1'). 매칭 0건이면 'unknown'."
    )
    event_template: str | None = Field(
        default=None,
        description="매칭된 템플릿 문자열(<*> 와일드카드 포함). unknown 이면 None.",
    )
    matched: bool = Field(
        default=False,
        description="템플릿 매칭 성공 여부. False 면 event_id='unknown'.",
    )


class _CompiledTemplate:
    """매칭 성능을 위해 regex 를 미리 컴파일한 템플릿."""

    def __init__(self, raw: dict) -> None:
        self.event_id: str = raw["event_id"]
        self.event_template: str = raw["event_template"]
        self.literal_len: int = int(raw.get("literal_len", 0))
        self.wildcard_count: int = int(raw.get("wildcard_count", 0))
        self.pattern: re.Pattern[str] = re.compile(raw["regex"])


class EventTemplateExtractor:
    """이벤트 템플릿 매칭기. ``templates`` 를 주입하면 테스트에서 격리 검증할 수 있다."""

    def __init__(self, templates: list[dict] | None = None) -> None:
        if templates is None:
            templates = list(_load_templates())
        self._templates = [_CompiledTemplate(t) for t in templates]

    def extract(self, content: str) -> EventTemplateResult:
        text = content.strip()
        matches = [t for t in self._templates if t.pattern.match(text)]
        if not matches:
            return EventTemplateResult(event_id=UNKNOWN_EVENT_ID, matched=False)

        # tie-break (우선순위): literal_len 내림차순 → wildcard_count 오름차순
        # → event_id 오름차순(동률 시 결정적 선택). min + (-literal_len) 으로 표현.
        best = min(
            matches,
            key=lambda t: (-t.literal_len, t.wildcard_count, t.event_id),
        )
        return EventTemplateResult(
            event_id=best.event_id,
            event_template=best.event_template,
            matched=True,
        )


@lru_cache
def _load_templates() -> tuple[dict, ...]:
    data = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    return tuple(data["templates"])


@lru_cache
def _default_extractor() -> EventTemplateExtractor:
    return EventTemplateExtractor()


def extract_event_template(content: str) -> EventTemplateResult:
    """기본 메타데이터를 사용해 ``content`` 의 이벤트 템플릿을 판정한다."""

    return _default_extractor().extract(content)
