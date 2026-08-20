import json

from app.services.chinese_profile_service import ChineseProfileService


def test_parse_profile_json_sanitizes_markdown_html_fields():
    service = ChineseProfileService()
    content = json.dumps(
        {
            "summary": "\u200b# Heading\u202e <h1>Injected</h1> ![badge](https://img.example/badge.svg) [docs](https://example.com)",
            "features": ["<b>Agent workflow</b>", "![badge](https://img.example/badge.svg)"],
            "audience": ["[Python developers](https://example.com)"],
            "highlights": ["[docs](https://example.com) GitHub stars; Matched tags: AI, Agent"],
            "status": "complete",
        },
        ensure_ascii=False,
    )

    parsed = service._parse_profile_json(content)

    assert parsed is not None
    assert parsed["summary"] == "Heading Injected docs"
    assert parsed["features"] == ["Agent workflow"]
    assert parsed["audience"] == ["Python developers"]
    assert parsed["highlights"] == ["docs"]


def test_parse_profile_json_removes_profile_boilerplate_and_star_count():
    service = ChineseProfileService()
    content = json.dumps(
        {
            "summary": (
                "koala73/worldmonitor 是一个与 AI/Agent 相关的开源项目,原始简介为:"
                "Real-time global intelligence dashboard. AI-powered news aggregation... "
                "项目当前拥有 82779 个 GitHub stars;命中标签:AI, Agent"
            ),
            "features": ["Agent workflow"],
            "audience": ["Python developers"],
            "highlights": ["docs"],
            "status": "complete",
        },
        ensure_ascii=False,
    )

    parsed = service._parse_profile_json(content)

    assert parsed is not None
    assert parsed["summary"] == (
        "koala73/worldmonitor Real-time global intelligence dashboard. AI-powered news aggregation..."
    )
