import json

from app.services.chinese_profile_service import ChineseProfileService


def test_parse_profile_json_sanitizes_markdown_html_fields():
    service = ChineseProfileService()
    content = json.dumps(
        {
            "summary": "# Heading <h1>Injected</h1> ![badge](https://img.example/badge.svg) [docs](https://example.com)",
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
