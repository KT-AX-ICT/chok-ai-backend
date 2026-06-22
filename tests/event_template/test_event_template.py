from app.agents.tools.event_template import (
    EventTemplateExtractor,
    extract_event_template,
)


def test_exact_match_returns_event_id() -> None:
    content = "12 ddr error(s) detected and corrected on rank 0, symbol 4 over 1234 seconds"

    result = extract_event_template(content)

    assert result.matched is True
    assert result.event_id == "E1"


def test_no_match_returns_unknown() -> None:
    result = extract_event_template("this content matches no known template xyz")

    assert result.matched is False
    assert result.event_id == "unknown"
    assert result.event_template is None


def test_ambiguous_match_prefers_more_specific_template() -> None:
    templates = [
        {
            "event_id": "GENERIC",
            "event_template": "<*> failed",
            "regex": r"^(.*?)\ failed$",
            "literal_len": 6,        },
        {
            "event_id": "SPECIFIC",
            "event_template": "job <*> failed",
            "regex": r"^job\ (.*?)\ failed$",
            "literal_len": 10,        },
    ]
    extractor = EventTemplateExtractor(templates=templates)

    result = extractor.extract("job 42 failed")

    assert result.event_id == "SPECIFIC"


def test_tie_break_prefers_fewer_wildcards_on_literal_len_tie() -> None:
    # 두 템플릿 모두 매칭되고 literal_len 동률(6) → wildcard_count 적은 쪽 선택.
    templates = [
        {
            "event_id": "MANYWILD",
            "event_template": "a <*> b <*> c",
            "regex": r"^a\ (.*?)\ b\ (.*?)\ c$",
            "literal_len": 6,
            "wildcard_count": 2,        },
        {
            "event_id": "FEWWILD",
            "event_template": "a <*> b x c",
            "regex": r"^a\ (.*?)\ b\ x\ c$",
            "literal_len": 6,
            "wildcard_count": 1,        },
    ]
    extractor = EventTemplateExtractor(templates=templates)

    result = extractor.extract("a 1 b x c")

    assert result.event_id == "FEWWILD"


def test_tie_break_is_deterministic_by_event_id_on_full_tie() -> None:
    # literal_len·wildcard_count 모두 동률 → event_id 오름차순으로 결정적 선택.
    # (리스트 순서가 아니라 event_id 로 결정됨을 증명하기 위해 ZZZ 를 먼저 배치)
    templates = [
        {
            "event_id": "E_ZZZ",
            "event_template": "<*> foo",
            "regex": r"^(.*?)\ foo$",
            "literal_len": 4,
            "wildcard_count": 1,        },
        {
            "event_id": "E_AAA",
            "event_template": "<*> foo",
            "regex": r"^(.*?)\ foo$",
            "literal_len": 4,
            "wildcard_count": 1,        },
    ]
    extractor = EventTemplateExtractor(templates=templates)

    result = extractor.extract("x foo")

    assert result.event_id == "E_AAA"
