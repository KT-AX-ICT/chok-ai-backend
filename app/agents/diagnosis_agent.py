"""
로그 근거 설명 / 정상 사유 작성 Agent

- 이상 로그: run_diagnosis() → summary / analysis / action
- 정상 로그: run_normal_reason() → summary / analysis (정상 사유)

LLM: OpenAI (langchain-openai)
구조화 출력: with_structured_output(...)
risk_level / cluster_id / event_id 는 결정적 Tool 산출값 → LLM이 바꾸지 않음.
"""

import asyncio
from functools import lru_cache
from typing import cast

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.agents.prompts.diagnosis import (
    NORMAL_SYSTEM_PROMPT,
    NORMAL_USER_PROMPT_TEMPLATE,
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
)
from app.core.config import get_settings
from app.core.errors import LLMError, LLMTimeoutError
from app.schemas.analysis import AnalyzeRequest, RiskLevel


class DiagnosisOutput(BaseModel):
    """이상 로그 — LLM이 채우는 텍스트 3필드."""

    summary: str = Field(..., min_length=1, description="이상 상황 한 문장 요약")
    analysis: str = Field(..., min_length=1, description="원인 분석 (추정 여부 명시)")
    action: str = Field(..., min_length=1, description="대응 방안")


class NormalReasonOutput(BaseModel):
    """정상 로그(FATAL→정상) — LLM이 채우는 정상 사유 2필드."""

    summary: str = Field(..., min_length=1, description="정상으로 판단한 핵심 사유")
    analysis: str = Field(..., min_length=1, description="정상 판단 근거")


@lru_cache
def _structured_llm(schema: type[BaseModel]):
    """LLM 클라이언트 + 구조화 출력 래퍼를 스키마별로 한 번만 빌드해 캐시."""
    settings = get_settings()

    if not settings.openai_api_key.get_secret_value():
        raise RuntimeError(
            "OPENAI_API_KEY가 비어있습니다. .env에 키를 설정한 뒤 서버를 재시작하세요."
        )

    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key,
        temperature=settings.llm_temperature,
        # max_tokens의 alias (langchain-openai). pyright/런타임 모두 호환
        max_completion_tokens=settings.llm_max_tokens,
    )
    return llm.with_structured_output(schema)


async def _ainvoke(schema: type[BaseModel], messages: list[BaseMessage]):
    """구조화 LLM 호출 — 타임아웃은 503, 그 외 실패는 502로 변환."""
    structured = _structured_llm(schema)
    try:
        return await structured.ainvoke(messages)
    except (asyncio.TimeoutError, TimeoutError) as e:
        raise LLMTimeoutError("LLM 응답 지연/타임아웃", str(e)) from e
    except Exception as e:
        raise LLMError("LLM 호출 또는 구조화 출력 실패", str(e)) from e


async def run_diagnosis(
    log: AnalyzeRequest,
    risk_level: RiskLevel,
    cluster_id: int,
    event_id: str,
    node_ctx: str,
) -> dict[str, str]:
    """이상 로그 한 건의 summary / analysis / action 생성."""
    user_prompt = USER_PROMPT_TEMPLATE.format(
        log_id=log.log_id,
        log_ts=log.log_ts,        # 통과형 문자열
        node=log.node,
        component=log.component,
        log_type=log.log_type,
        log_level=log.log_level,
        event_id=event_id,
        content=log.content,
        risk_level=risk_level,
        cluster_id=cluster_id,
        node_ctx=node_ctx,
    )

    result = cast(
        DiagnosisOutput,
        await _ainvoke(
            DiagnosisOutput,
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=user_prompt),
            ],
        ),
    )
    return result.model_dump()


async def run_normal_reason(
    log: AnalyzeRequest,
    event_id: str,
) -> dict[str, str]:
    """정상 로그(FATAL→정상) 한 건의 정상 사유 summary / analysis 생성."""
    user_prompt = NORMAL_USER_PROMPT_TEMPLATE.format(
        log_id=log.log_id,
        log_ts=log.log_ts,
        node=log.node,
        component=log.component,
        log_type=log.log_type,
        log_level=log.log_level,
        event_id=event_id,
        content=log.content,
    )

    result = cast(
        NormalReasonOutput,
        await _ainvoke(
            NormalReasonOutput,
            [
                SystemMessage(content=NORMAL_SYSTEM_PROMPT),
                HumanMessage(content=user_prompt),
            ],
        ),
    )
    return result.model_dump()
