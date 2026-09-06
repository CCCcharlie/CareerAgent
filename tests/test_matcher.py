from agent.matcher import ResumeMatcher


def test_parse_json_uses_weighted_score_and_preserves_full_result():
    result = ResumeMatcher._parse_json(
        '''{
            "score": 2,
            "weighted_score": 8.25,
            "reason": "strong fit",
            "selected_resume": "dev",
            "dimension_scores": {"technical_skills": 9},
            "analysis": "matched Python experience"
        }'''
    )

    assert result == {
        "score": 8.25,
        "reason": "strong fit",
        "selected_resume": "dev",
        "dimension_scores": {"technical_skills": 9},
        "analysis": "matched Python experience",
    }


def test_parse_json_accepts_fenced_json():
    result = ResumeMatcher._parse_json(
        '```json\n{"score": 7, "reason": "good"}\n```'
    )

    assert result["score"] == 7.0
    assert result["reason"] == "good"
    assert result["selected_resume"] == "unknown"


def test_parse_json_extracts_object_surrounded_by_text():
    result = ResumeMatcher._parse_json(
        'Model result: {"score": 6.5, "reason": "usable", "analysis": "note"} End.'
    )

    assert result["score"] == 6.5
    assert result["reason"] == "usable"
    assert result["analysis"] == "note"


def test_parse_json_falls_back_for_nonstandard_score_text():
    result = ResumeMatcher._parse_json('score: 12, reason: strong candidate')

    assert result["score"] == 10.0
    assert result["reason"] == "strong candidate"


def test_parse_json_returns_safe_fallback_for_invalid_output():
    assert ResumeMatcher._parse_json("not JSON at all") == {
        "score": 5,
        "reason": "解析失败",
    }


def test_parse_json_returns_safe_fallback_for_non_object_json():
    assert ResumeMatcher._parse_json("[]") == {
        "score": 5,
        "reason": "解析失败",
    }


def test_parse_json_replaces_non_dict_dimension_scores():
    result = ResumeMatcher._parse_json(
        '{"score": 6, "reason": "ok", "dimension_scores": [1, 2]}'
    )

    assert result["score"] == 6.0
    assert result["dimension_scores"] == {}
