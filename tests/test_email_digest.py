from sqlalchemy import func, select  # 查询日报、投递记录数量。
from sqlalchemy.orm import Session  # 类型标注测试数据库会话。

from app.db.models import EmailDelivery, EmailReport  # 用来断言邮件日报和投递记录。
from app.services.email_digest_service import EmailDigestService  # 测试中替换真实 SMTP 发送。


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
