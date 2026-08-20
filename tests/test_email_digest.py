from types import SimpleNamespace

from sqlalchemy import func, select  # 查询日报、投递记录数量。
from sqlalchemy.orm import Session  # 类型标注测试数据库会话。

from app.db.models import EmailDelivery, EmailReport, ProjectProfile  # 用来断言邮件日报和投递记录。
from app.services.email_digest_service import EmailDigestService  # 测试中替换真实 SMTP 发送。


def test_email_digest_builder_sanitizes_markdown_html_profile_content(fixed_report_date):
    """邮件内容构建器本身就要挡住 Markdown/HTML 污染，不依赖数据库才安全。"""
    service = EmailDigestService(db=None)
    repository = SimpleNamespace(
        full_name="dirty/profile-demo",
        html_url='https://github.com/dirty/profile-demo?next=<script>',
        primary_language="Python",
        description="safe fallback",
        profile=SimpleNamespace(
            summary=(
                "# Dirty Title <h1>Injected</h1> ![badge](https://img.example/badge.svg) "
                "[quick start](https://example.com/docs) "
                + "A" * 200
            ),
            highlights=[
                '<p align="center">Centered headline</p>',
                "![GitHub stars](https://img.example/stars.svg)",
                "[docs](https://example.com) GitHub stars; Matched tags: AI, Agent",
            ],
        ),
    )
    hot_project = SimpleNamespace(
        rank_no=1,
        repository=repository,
        stars=123,
        stars_delta_24h=12,
        stars_delta_7d=35,
        reason="测试热点项目。",
    )

    html_content = service._build_html_content(fixed_report_date, [hot_project])
    text_content = service._build_text_content(fixed_report_date, [hot_project])

    assert "dirty/profile-demo" in html_content
    assert "quick start" in html_content
    assert "quick start" in text_content
    assert "https://github.com/dirty/profile-demo?next=" in html_content
    assert "<script>" not in html_content
    for polluted in ("<h1>", "</h1>", "# Dirty Title", "![", "](", "<p", "</p>", "GitHub stars", "Matched tags"):
        assert polluted not in html_content
        assert polluted not in text_content


def test_email_digest_builder_adds_mobile_responsive_layout(fixed_report_date):
    """邮件 HTML 要带移动端断点，避免窄屏把项目名压成一列。"""
    service = EmailDigestService(db=None)
    repository = SimpleNamespace(
        full_name="deepseek-ai/deepseek-harness",
        html_url="https://github.com/deepseek-ai/deepseek-harness",
        primary_language="TypeScript",
        description="safe fallback",
        profile=SimpleNamespace(summary="DeepSeek Harness: Everything is a Plugin.", highlights=["Composable agents."]),
    )
    hot_project = SimpleNamespace(
        rank_no=1,
        repository=repository,
        stars=123,
        stars_delta_24h=12,
        stars_delta_7d=35,
        reason="测试热点项目。",
    )

    html_content = service._build_html_content(fixed_report_date, [hot_project])

    assert 'meta name="viewport"' in html_content
    assert "@media only screen and (max-width: 640px)" in html_content
    assert 'class="digest-table"' in html_content
    assert 'class="project-cell"' in html_content
    assert 'class="repo-name"' in html_content
    assert 'class="metric-cell"' in html_content


def test_email_digest_dry_run_creates_report_without_deliveries(
    client,
    db_session: Session,
    fixed_report_date,
    hot_project_factory,
    subscriber_factory,
):
    """dry_run 只生成日报内容，不应创建投递记录。"""
    hot_project_factory(report_date=fixed_report_date)
    subscriber_factory("dry-run@example.com")

    response = client.post(
        "/api/v1/email-digests/runs",
        json={"report_date": fixed_report_date.isoformat(), "top_n": 20, "dry_run": True},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["dry_run"] is True
    assert body["status"] == "draft"
    assert body["subscriber_count"] == 0
    assert body["deliveries"] == []

    report = db_session.scalar(select(EmailReport).where(EmailReport.report_date == fixed_report_date))
    assert report is not None
    assert report.status == "draft"
    delivery_count = db_session.scalar(select(func.count(EmailDelivery.id)))
    assert delivery_count == 0


def test_email_digest_repeated_send_reuses_delivery(
    client,
    db_session: Session,
    fixed_report_date,
    hot_project_factory,
    subscriber_factory,
    monkeypatch,
):
    """同一天重复正式发送日报时，应复用旧投递记录而不是返回 500。"""
    hot_project_factory(report_date=fixed_report_date)
    subscriber_factory("repeat@example.com")
    sent_emails: list[str] = []

    def fake_send_email(self: EmailDigestService, to_email: str, subject: str, text_content: str, html_content: str) -> None:
        # 记录调用次数即可，不连接真实 SMTP。
        sent_emails.append(to_email)

    monkeypatch.setattr(EmailDigestService, "_send_email", fake_send_email)

    first_response = client.post(
        "/api/v1/email-digests/runs",
        json={"report_date": fixed_report_date.isoformat(), "top_n": 20, "dry_run": False},
    )
    second_response = client.post(
        "/api/v1/email-digests/runs",
        json={"report_date": fixed_report_date.isoformat(), "top_n": 20, "dry_run": False},
    )

    assert first_response.status_code == 201, first_response.text
    assert second_response.status_code == 201, second_response.text
    assert first_response.json()["sent_count"] == 1
    assert second_response.json()["sent_count"] == 1
    assert sent_emails == ["repeat@example.com", "repeat@example.com"]

    deliveries = list(db_session.scalars(select(EmailDelivery)).all())
    assert len(deliveries) == 1
    assert deliveries[0].email == "repeat@example.com"
    assert deliveries[0].status == "sent"
    assert deliveries[0].retry_count == 1


def test_email_digest_sanitizes_markdown_html_profile_content(
    client,
    db_session: Session,
    fixed_report_date,
    hot_project_factory,
    repository_factory,
):
    """邮件日报不应把 README/Markdown/HTML 污染内容原样渲染出来。"""
    repository = repository_factory(full_name="dirty/profile-demo")
    profile = ProjectProfile(
        repository_id=repository.id,
        summary=(
            "# Dirty Title <h1>Injected</h1> ![badge](https://img.example/badge.svg) "
            "[quick start](https://example.com/docs) "
            + "A" * 200
        ),
        features=[],
        audience=[],
        highlights=[
            '<p align="center">Centered headline</p>',
            "![GitHub stars](https://img.example/stars.svg)",
            "[docs](https://example.com) GitHub stars; Matched tags: AI, Agent",
        ],
        tech_stack={},
        readme_hash="dirty-readme",
        summary_status="complete",
    )
    db_session.add(profile)
    db_session.commit()
    hot_project_factory(report_date=fixed_report_date, repository=repository)

    response = client.post(
        "/api/v1/email-digests/runs",
        json={"report_date": fixed_report_date.isoformat(), "top_n": 20, "dry_run": True},
    )

    assert response.status_code == 201, response.text
    report = db_session.scalar(select(EmailReport).where(EmailReport.report_date == fixed_report_date))
    assert report is not None

    assert "dirty/profile-demo" in report.html_content
    assert "quick start" in report.html_content
    assert "quick start" in report.text_content
    for polluted in ("<h1>", "</h1>", "# Dirty Title", "![", "](", "<p", "</p>", "GitHub stars", "Matched tags"):
        assert polluted not in report.html_content
        assert polluted not in report.text_content
