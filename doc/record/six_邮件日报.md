# 计划 7：邮件日报代码方案

## Summary
第 7 步实现“邮件日报”：从 `hot_projects` 读取某天热点榜，生成 HTML/纯文本邮件内容，保存到 `email_reports`，给 `subscribers.status='active'` 的订阅者发送邮件，并写入 `email_deliveries` 投递记录。

本阶段先做**手动触发发送**，不做后台定时任务。后续如果要定时发送，再把这个 service 接到调度器即可。

## Key Changes
需要新增/修改：

- 修改 `app/db/models.py`
  - 新增 `Subscriber`
  - 新增 `EmailReport`
  - 新增 `EmailDelivery`
- 新增 `app/schemas/email_digest.py`
- 新增 `app/services/email_digest_service.py`
- 新增 `app/api/routes_email_digest.py`
- 修改 `app/main.py` 注册邮件日报路由

## Code

### 1. 修改 `app/db/models.py`

在 `HotProject` 类后、`Job` 类前，新增下面三个 ORM 模型：

```python
class Subscriber(Base):  # Subscriber 类对应 subscribers 表。
    """
    subscribers 表的 ORM 模型。

    这张表保存邮件订阅者。
    只有 status='active' 的订阅者，才会收到日报。
    """

    __tablename__ = "subscribers"  # 告诉 SQLAlchemy：这个类对应 subscribers 表。

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)  # 订阅者主键，使用 UUID 字符串。

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)  # 订阅者邮箱，unique=True 避免重复订阅。

    name: Mapped[str | None] = mapped_column(String(255))  # 订阅者名称，可以为空。

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")  # 订阅状态：active、paused、unsubscribed。

    preferences: Mapped[dict] = mapped_column(  # 订阅偏好，后续可保存语言、主题、数量等配置。
        MutableDict.as_mutable(JSON),  # JSON 字典使用 MutableDict，方便 ORM 识别内部修改。
        nullable=False,  # 不允许为空，保证业务代码总能拿到 dict。
        default=dict,  # 默认空字典，表示暂无偏好。
    )

    unsubscribe_token: Mapped[str] = mapped_column(String(36), nullable=False, default=uuid_str, unique=True)  # 退订 token，后续做退订链接用。

    unsubscribed_at: Mapped[datetime | None] = mapped_column(DateTime)  # 退订时间，未退订时为空。

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())  # 创建时间。

    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())  # 更新时间。


class EmailReport(Base):  # EmailReport 类对应 email_reports 表。
    """
    email_reports 表的 ORM 模型。

    这张表保存每天生成出来的日报内容。
    一天只生成一份报告，发送给多个订阅者。
    """

    __tablename__ = "email_reports"  # 告诉 SQLAlchemy：这个类对应 email_reports 表。

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)  # 邮件日报主键。

    report_date: Mapped[date] = mapped_column(Date, nullable=False, unique=True)  # 日报日期，一天只允许一份报告。

    subject: Mapped[str] = mapped_column(String(255), nullable=False)  # 邮件标题。

    html_content: Mapped[str] = mapped_column(Text, nullable=False)  # HTML 邮件内容。

    text_content: Mapped[str] = mapped_column(Text, nullable=False)  # 纯文本邮件内容。

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")  # 报告状态：draft、sending、sent、failed。

    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())  # 生成时间。

    sent_at: Mapped[datetime | None] = mapped_column(DateTime)  # 发送完成时间。

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())  # 创建时间。

    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())  # 更新时间。

    deliveries: Mapped[list["EmailDelivery"]] = relationship(  # 一份日报会发给多个订阅者，所以有多条投递记录。
        back_populates="report",  # 和 EmailDelivery.report 配对。
        cascade="all, delete-orphan",  # 删除日报时，同步删除对应投递记录。
    )


class EmailDelivery(Base):  # EmailDelivery 类对应 email_deliveries 表。
    """
    email_deliveries 表的 ORM 模型。

    这张表保存每个订阅者的发送结果。
    同一份日报发给 10 个人，就会有 10 条投递记录。
    """

    __tablename__ = "email_deliveries"  # 告诉 SQLAlchemy：这个类对应 email_deliveries 表。

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)  # 投递记录主键。

    report_id: Mapped[str] = mapped_column(String(36), ForeignKey("email_reports.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False)  # 关联 email_reports.id。

    subscriber_id: Mapped[str] = mapped_column(String(36), ForeignKey("subscribers.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False)  # 关联 subscribers.id。

    email: Mapped[str] = mapped_column(String(320), nullable=False)  # 实际发送邮箱，冗余保存方便排查。

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # 发送状态：pending、sending、sent、failed、skipped。

    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 重试次数，本阶段先不做自动重试。

    error_message: Mapped[str | None] = mapped_column(Text)  # 失败原因，成功时为空。

    sent_at: Mapped[datetime | None] = mapped_column(DateTime)  # 发送成功时间。

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())  # 创建时间。

    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())  # 更新时间。

    report: Mapped[EmailReport] = relationship(back_populates="deliveries")  # 反向关联到 EmailReport。

    subscriber: Mapped[Subscriber] = relationship()  # 反向关联到 Subscriber，方便通过 delivery.subscriber 访问订阅者。

    __table_args__ = (  # 表级配置。
        UniqueConstraint("report_id", "subscriber_id", name="uq_email_deliveries_report_subscriber"),  # 同一份日报给同一订阅者只能有一条投递记录。
    )
```

注意：如果你的 `models.py` 顶部还没有导入 `Date`，需要保证有：

```python
from sqlalchemy import Date
```

### 2. 新增 `app/schemas/email_digest.py`

```python
from datetime import date, datetime  # date 表示日报日期；datetime 表示生成/发送时间。

from pydantic import BaseModel, EmailStr, Field  # BaseModel 定义模型；EmailStr 校验邮箱格式；Field 写说明。


class SubscriberCreate(BaseModel):  # 新增订阅者请求体。
    """新增订阅者请求体。"""

    email: EmailStr = Field(..., description="订阅者邮箱。")  # 邮箱必填，并自动校验格式。

    name: str | None = Field(default=None, description="订阅者名称，可为空。")  # 名称可选。


class SubscriberResponse(BaseModel):  # 订阅者响应体。
    """订阅者响应体。"""

    id: str  # 订阅者 id。

    email: str  # 订阅者邮箱。

    name: str | None = None  # 订阅者名称。

    status: str  # 订阅状态。

    created_at: datetime  # 创建时间。

    model_config = {"from_attributes": True}  # 允许从 SQLAlchemy ORM 对象直接转换。


class EmailDigestRunRequest(BaseModel):  # 手动发送日报请求体。
    """手动发送邮件日报请求体。"""

    report_date: date | None = Field(default=None, description="日报日期；不传则发送今天的热点榜。")  # 不传默认今天。

    top_n: int = Field(default=20, ge=1, le=100, description="邮件里展示前 N 个热点项目。")  # 控制邮件内容数量。

    dry_run: bool = Field(default=False, description="是否只生成报告不发送邮件。")  # True 时只生成 email_reports，不发送。


class EmailDeliveryResponse(BaseModel):  # 单条投递记录响应体。
    """邮件投递记录响应体。"""

    id: str  # 投递记录 id。

    email: str  # 实际发送邮箱。

    status: str  # 发送状态。

    error_message: str | None = None  # 失败原因。

    sent_at: datetime | None = None  # 发送时间。

    model_config = {"from_attributes": True}  # 允许从 ORM 对象转换。


class EmailDigestRunResponse(BaseModel):  # 手动发送日报响应体。
    """邮件日报发送结果响应体。"""

    report_id: str  # email_reports 表 id。

    report_date: date  # 日报日期。

    subject: str  # 邮件标题。

    status: str  # 报告状态。

    subscriber_count: int  # 目标订阅者数量。

    sent_count: int  # 成功发送数量。

    failed_count: int  # 失败数量。

    dry_run: bool  # 是否为只生成不发送。

    deliveries: list[EmailDeliveryResponse]  # 投递记录列表。
```

如果你没有装 `email-validator`，`EmailStr` 会报依赖错误。那就在 `requirements.txt` 加：

```txt
email-validator>=2.2.0
```

或者先把 `EmailStr` 改成普通 `str`。

### 3. 新增 `app/services/email_digest_service.py`

```python
import smtplib  # Python 标准库 SMTP 客户端，用来真正发送邮件。
from datetime import UTC, date, datetime  # UTC 统一时间；date 表示日报日期；datetime 记录发送时间。
from email.message import EmailMessage  # 用来构造一封同时包含纯文本和 HTML 的邮件。

from sqlalchemy import select  # SQLAlchemy 2.x 推荐查询写法。
from sqlalchemy.orm import Session  # 数据库会话类型。

from app.core.config import settings  # 读取 SMTP、发件人等配置。
from app.db.models import EmailDelivery, EmailReport, HotProject, Subscriber  # 导入邮件、热点、订阅者 ORM 模型。


class EmailDigestService:  # 邮件日报业务服务。
    """生成并发送 GitHub 热点项目日报。"""

    def __init__(self, db: Session) -> None:  # 初始化时传入数据库会话。
        self.db = db  # 保存数据库会话，后续查询、写入都使用它。

    def create_subscriber(self, email: str, name: str | None = None) -> Subscriber:  # 新增订阅者。
        existing = self.get_subscriber_by_email(email)  # 先根据邮箱查重，避免重复插入。
        if existing:  # 如果已经存在。
            return existing  # 直接返回已有订阅者，让接口具备幂等性。

        subscriber = Subscriber(  # 创建订阅者 ORM 对象。
            email=email,  # 保存邮箱。
            name=name,  # 保存名称。
            status="active",  # 新增订阅者默认 active。
            preferences={},  # 当前阶段没有订阅偏好，先保存空字典。
        )
        self.db.add(subscriber)  # 加入数据库会话。
        self.db.commit()  # 提交到 MySQL。
        self.db.refresh(subscriber)  # 刷新对象，拿到数据库生成字段。
        return subscriber  # 返回订阅者对象。

    def get_subscriber_by_email(self, email: str) -> Subscriber | None:  # 根据邮箱查订阅者。
        statement = select(Subscriber).where(Subscriber.email == email)  # 构造查询语句。
        return self.db.scalar(statement)  # 查到返回 Subscriber，查不到返回 None。

    def list_subscribers(self) -> list[Subscriber]:  # 查询订阅者列表。
        statement = select(Subscriber).order_by(Subscriber.created_at.desc())  # 按创建时间倒序。
        return list(self.db.scalars(statement).all())  # 返回列表。

    def run_digest(self, report_date: date | None = None, top_n: int = 20, dry_run: bool = False) -> dict:  # 手动生成/发送日报。
        current_report_date = report_date or datetime.now(UTC).date()  # 不传日期时使用今天。
        hot_projects = self._load_hot_projects(current_report_date, top_n)  # 查询当天热点榜。
        subscribers = self._load_active_subscribers()  # 查询 active 订阅者。

        subject = f"GitHub 热点项目日报 - {current_report_date.isoformat()}"  # 生成邮件标题。
        html_content = self._build_html_content(current_report_date, hot_projects)  # 生成 HTML 内容。
        text_content = self._build_text_content(current_report_date, hot_projects)  # 生成纯文本内容。

        report = self._create_or_update_report(current_report_date, subject, html_content, text_content)  # 保存或更新日报内容。
        deliveries: list[EmailDelivery] = []  # 保存投递记录。
        sent_count = 0  # 成功发送数量。
        failed_count = 0  # 失败数量。

        if dry_run:  # 如果只是预演。
            report.status = "draft"  # 只生成报告，不进入发送状态。
            self.db.commit()  # 保存报告状态。
            return self._build_response(report, [], 0, 0, True)  # 返回 dry_run 结果。

        report.status = "sending"  # 开始发送前，把报告状态改成 sending。
        self.db.commit()  # 提交状态，方便中途排查。

        for subscriber in subscribers:  # 遍历所有 active 订阅者。
            delivery = EmailDelivery(  # 创建一条投递记录。
                report_id=report.id,  # 关联本次日报。
                subscriber_id=subscriber.id,  # 关联订阅者。
                email=subscriber.email,  # 冗余保存实际发送邮箱。
                status="sending",  # 当前正在发送。
                retry_count=0,  # 本阶段不做自动重试。
            )
            self.db.add(delivery)  # 加入数据库会话。
            self.db.commit()  # 先提交投递记录，确保失败也能查到。
            self.db.refresh(delivery)  # 刷新投递记录。

            try:  # 单个订阅者失败不影响其他订阅者。
                self._send_email(subscriber.email, subject, text_content, html_content)  # 真正发送邮件。
                delivery.status = "sent"  # 发送成功。
                delivery.sent_at = datetime.now(UTC)  # 记录发送时间。
                delivery.error_message = None  # 成功时错误为空。
                sent_count += 1  # 成功数量加 1。
            except Exception as exc:  # 捕获 SMTP 连接、认证、发送等错误。
                delivery.status = "failed"  # 标记失败。
                delivery.error_message = str(exc)  # 保存失败原因。
                failed_count += 1  # 失败数量加 1。

            self.db.commit()  # 提交当前订阅者投递结果。
            self.db.refresh(delivery)  # 刷新投递记录。
            deliveries.append(delivery)  # 加入返回列表。

        report.status = "sent" if failed_count == 0 else "failed"  # 全部成功才算 sent，否则 failed。
        report.sent_at = datetime.now(UTC)  # 记录本轮发送结束时间。
        self.db.commit()  # 提交报告最终状态。
        self.db.refresh(report)  # 刷新报告。

        return self._build_response(report, deliveries, sent_count, failed_count, False)  # 返回接口响应。

    def _load_hot_projects(self, report_date: date, top_n: int) -> list[HotProject]:  # 查询当天热点项目。
        statement = (  # 构造查询语句。
            select(HotProject)  # 查询 hot_projects 表。
            .where(HotProject.report_date == report_date)  # 只查指定日期。
            .order_by(HotProject.rank_no.asc())  # 按排名升序。
            .limit(top_n)  # 只取前 top_n 条。
        )
        return list(self.db.scalars(statement).all())  # 返回热点项目列表。

    def _load_active_subscribers(self) -> list[Subscriber]:  # 查询 active 订阅者。
        statement = (  # 构造查询语句。
            select(Subscriber)  # 查询 subscribers 表。
            .where(Subscriber.status == "active")  # 只给 active 用户发邮件。
            .order_by(Subscriber.created_at.asc())  # 按订阅时间排序。
        )
        return list(self.db.scalars(statement).all())  # 返回订阅者列表。

    def _create_or_update_report(self, report_date: date, subject: str, html_content: str, text_content: str) -> EmailReport:  # 保存日报。
        statement = select(EmailReport).where(EmailReport.report_date == report_date)  # 同一天只允许一份报告。
        report = self.db.scalar(statement)  # 查询已有报告。

        if report is None:  # 如果当天还没有报告。
            report = EmailReport(report_date=report_date, subject=subject, html_content=html_content, text_content=text_content, status="draft")  # 创建新报告。
            self.db.add(report)  # 加入数据库会话。
        else:  # 如果当天已经有报告。
            report.subject = subject  # 更新标题。
            report.html_content = html_content  # 更新 HTML 内容。
            report.text_content = text_content  # 更新纯文本内容。
            report.status = "draft"  # 重新生成后先回到 draft。

        self.db.commit()  # 提交报告。
        self.db.refresh(report)  # 刷新报告。
        return report  # 返回报告对象。

    def _build_text_content(self, report_date: date, hot_projects: list[HotProject]) -> str:  # 生成纯文本邮件。
        lines = [f"GitHub 热点项目日报 - {report_date.isoformat()}", ""]  # 邮件标题行。
        if not hot_projects:  # 如果当天没有热点项目。
            lines.append("今日暂无热点项目，请先执行热点计算。")  # 提醒先跑第 6 步。
            return "\n".join(lines)  # 返回纯文本内容。

        for item in hot_projects:  # 遍历热点项目。
            repo = item.repository  # 通过 ORM 关系拿到仓库信息。
            lines.append(f"{item.rank_no}. {repo.full_name}")  # 排名和仓库名。
            lines.append(f"   Stars: {item.stars}，24h +{item.stars_delta_24h}，7d +{item.stars_delta_7d}")  # 指标。
            lines.append(f"   语言: {repo.primary_language or '未知'}")  # 主语言。
            lines.append(f"   地址: {repo.html_url}")  # GitHub 地址。
            lines.append(f"   原因: {item.reason or '暂无'}")  # 入选原因。
            lines.append("")  # 空行分隔。
        return "\n".join(lines)  # 拼成纯文本。

    def _build_html_content(self, report_date: date, hot_projects: list[HotProject]) -> str:  # 生成 HTML 邮件。
        rows = []  # 保存每个项目的 HTML 块。
        for item in hot_projects:  # 遍历热点项目。
            repo = item.repository  # 通过 ORM 关系拿到仓库信息。
            rows.append(  # 添加一个项目块。
                f"""
                <tr>
                    <td style="padding:8px;border-bottom:1px solid #eee;">{item.rank_no}</td>
                    <td style="padding:8px;border-bottom:1px solid #eee;">
                        <a href="{repo.html_url}" target="_blank">{repo.full_name}</a><br>
                        <span style="color:#666;">{repo.description or ""}</span>
                    </td>
                    <td style="padding:8px;border-bottom:1px solid #eee;">{repo.primary_language or "未知"}</td>
                    <td style="padding:8px;border-bottom:1px solid #eee;">{item.stars}</td>
                    <td style="padding:8px;border-bottom:1px solid #eee;">+{item.stars_delta_24h}</td>
                    <td style="padding:8px;border-bottom:1px solid #eee;">+{item.stars_delta_7d}</td>
                </tr>
                """
            )

        table_body = "\n".join(rows) if rows else '<tr><td colspan="6" style="padding:8px;">今日暂无热点项目，请先执行热点计算。</td></tr>'  # 没数据时展示提示。

        return f"""
        <html>
        <body style="font-family:Arial,'Microsoft YaHei',sans-serif;color:#222;">
            <h2>GitHub 热点项目日报 - {report_date.isoformat()}</h2>
            <table style="border-collapse:collapse;width:100%;font-size:14px;">
                <thead>
                    <tr>
                        <th style="text-align:left;padding:8px;border-bottom:2px solid #ddd;">排名</th>
                        <th style="text-align:left;padding:8px;border-bottom:2px solid #ddd;">项目</th>
                        <th style="text-align:left;padding:8px;border-bottom:2px solid #ddd;">语言</th>
                        <th style="text-align:left;padding:8px;border-bottom:2px solid #ddd;">Stars</th>
                        <th style="text-align:left;padding:8px;border-bottom:2px solid #ddd;">24h</th>
                        <th style="text-align:left;padding:8px;border-bottom:2px solid #ddd;">7d</th>
                    </tr>
                </thead>
                <tbody>
                    {table_body}
                </tbody>
            </table>
        </body>
        </html>
        """  # 返回完整 HTML。

    def _send_email(self, to_email: str, subject: str, text_content: str, html_content: str) -> None:  # 发送单封邮件。
        if not settings.smtp_host:  # SMTP_HOST 必须配置。
            raise ValueError("SMTP_HOST 未配置。")  # 没配置就抛错。
        if not settings.smtp_username:  # SMTP_USERNAME 必须配置。
            raise ValueError("SMTP_USERNAME 未配置。")  # 没配置就抛错。
        if not settings.smtp_password:  # SMTP_PASSWORD 必须配置。
            raise ValueError("SMTP_PASSWORD 未配置。")  # 没配置就抛错。

        from_email = settings.mail_from or settings.smtp_username  # 发件人邮箱，不配置 MAIL_FROM 时使用 SMTP_USERNAME。
        message = EmailMessage()  # 创建邮件对象。
        message["Subject"] = subject  # 邮件标题。
        message["From"] = f"{settings.mail_from_name} <{from_email}>"  # 发件人展示名。
        message["To"] = to_email  # 收件人。
        message.set_content(text_content)  # 设置纯文本内容，兼容不支持 HTML 的客户端。
        message.add_alternative(html_content, subtype="html")  # 添加 HTML 内容。

        if settings.smtp_use_ssl:  # 465 端口通常使用 SSL。
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:  # 建立 SSL SMTP 连接。
                smtp.login(settings.smtp_username, settings.smtp_password)  # 登录 SMTP。
                smtp.send_message(message)  # 发送邮件。
        else:  # 非 SSL 模式。
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:  # 建立普通 SMTP 连接。
                if settings.smtp_use_tls:  # 587 端口通常需要 STARTTLS。
                    smtp.starttls()  # 开启 TLS。
                smtp.login(settings.smtp_username, settings.smtp_password)  # 登录 SMTP。
                smtp.send_message(message)  # 发送邮件。

    def _build_response(self, report: EmailReport, deliveries: list[EmailDelivery], sent_count: int, failed_count: int, dry_run: bool) -> dict:  # 组装接口响应。
        return {
            "report_id": report.id,  # 报告 id。
            "report_date": report.report_date,  # 报告日期。
            "subject": report.subject,  # 邮件标题。
            "status": report.status,  # 报告状态。
            "subscriber_count": len(deliveries),  # 本次实际生成投递记录数量。
            "sent_count": sent_count,  # 成功数量。
            "failed_count": failed_count,  # 失败数量。
            "dry_run": dry_run,  # 是否预演。
            "deliveries": deliveries,  # 投递记录列表。
        }
```

### 4. 新增 `app/api/routes_email_digest.py`

```python
from fastapi import APIRouter, Depends, status  # APIRouter 定义路由；Depends 注入依赖；status 提供状态码。
from sqlalchemy.orm import Session  # Session 用来标注数据库会话类型。

from app.db.session import get_db  # get_db 为每次请求提供数据库会话。
from app.schemas.email_digest import EmailDigestRunRequest, EmailDigestRunResponse, SubscriberCreate, SubscriberResponse  # 导入请求体和响应体。
from app.services.email_digest_service import EmailDigestService  # 导入邮件日报业务服务。


router = APIRouter(prefix="/email-digests", tags=["email_digests"])  # 当前文件接口统一以 /email-digests 开头。


@router.post("/subscribers", response_model=SubscriberResponse, status_code=status.HTTP_201_CREATED)  # POST /email-digests/subscribers 新增订阅者。
def create_subscriber(payload: SubscriberCreate, db: Session = Depends(get_db)) -> SubscriberResponse:  # 接收请求体和数据库会话。
    service = EmailDigestService(db)  # 创建业务服务对象。
    return service.create_subscriber(str(payload.email), payload.name)  # 创建订阅者并返回。


@router.get("/subscribers", response_model=list[SubscriberResponse])  # GET /email-digests/subscribers 查询订阅者列表。
def list_subscribers(db: Session = Depends(get_db)) -> list[SubscriberResponse]:  # 注入数据库会话。
    service = EmailDigestService(db)  # 创建业务服务对象。
    return service.list_subscribers()  # 返回订阅者列表。


@router.post("/runs", response_model=EmailDigestRunResponse, status_code=status.HTTP_201_CREATED)  # POST /email-digests/runs 手动生成/发送日报。
def run_email_digest(payload: EmailDigestRunRequest, db: Session = Depends(get_db)) -> EmailDigestRunResponse:  # 接收请求体和数据库会话。
    service = EmailDigestService(db)  # 创建业务服务对象。
    return service.run_digest(payload.report_date, payload.top_n, payload.dry_run)  # 执行日报生成/发送。
```

### 5. 修改 `app/main.py`

```python
from fastapi import FastAPI  # FastAPI 是应用入口类。

from app.api.routes_email_digest import router as email_digest_router  # 邮件日报路由。
from app.api.routes_health import router as health_router  # 健康检查路由。
from app.api.routes_hot_projects import router as hot_projects_router  # 热点项目路由。
from app.api.routes_repositories import router as repositories_router  # 仓库管理路由。
from app.api.routes_star_snapshots import router as star_snapshots_router  # 星标快照路由。
from app.core.config import settings  # 应用配置。


app = FastAPI(  # 创建 FastAPI 应用。
    title=settings.app_name,  # 应用名称。
    version=settings.app_version,  # 应用版本。
    docs_url="/docs",  # Swagger 文档地址。
    openapi_url="/openapi.json",  # OpenAPI JSON 地址。
)

app.include_router(health_router, prefix="/api/v1")  # 注册健康检查接口。
app.include_router(repositories_router, prefix="/api/v1")  # 注册仓库接口。
app.include_router(star_snapshots_router, prefix="/api/v1")  # 注册星标快照接口。
app.include_router(hot_projects_router, prefix="/api/v1")  # 注册热点项目接口。
app.include_router(email_digest_router, prefix="/api/v1")  # 注册邮件日报接口。


@app.get("/", include_in_schema=False)  # 根路径接口，不放进接口文档。
def root() -> dict[str, str]:  # 返回服务基础信息。
    return {
        "service": settings.app_name,
        "docs": "/docs",
        "health": "/api/v1/health",
    }
```

## API Usage
先新增订阅者：

```text
POST /api/v1/email-digests/subscribers
```

```json
{
  "email": "你的邮箱@163.com",
  "name": "测试用户"
}
```

只生成邮件内容、不发送：

```text
POST /api/v1/email-digests/runs
```

```json
{
  "top_n": 20,
  "dry_run": true
}
```

真正发送：

```json
{
  "top_n": 20,
  "dry_run": false
}
```

查询订阅者：

```text
GET /api/v1/email-digests/subscribers
```

## Test Plan
1. 确认 `.env` 已配置网易邮箱 SMTP：

```env
SMTP_HOST=smtp.163.com
SMTP_PORT=465
SMTP_USERNAME=你的网易邮箱
SMTP_PASSWORD=你的授权码
SMTP_USE_SSL=true
SMTP_USE_TLS=false
MAIL_FROM=你的网易邮箱
MAIL_FROM_NAME=GitHub 热点项目日报
```

2. 先保证第 6 步已有热点榜：

```sql
SELECT report_date, rank_no, repository_id, hot_score
FROM hot_projects
ORDER BY report_date DESC, rank_no ASC;
```

3. 新增订阅者。

4. 先 dry run：

```json
{
  "top_n": 20,
  "dry_run": true
}
```

验证：

```sql
SELECT report_date, subject, status
FROM email_reports
ORDER BY created_at DESC
LIMIT 5;
```

5. 再真实发送：

```json
{
  "top_n": 20,
  "dry_run": false
}
```

验证：

```sql
SELECT email, status, error_message, sent_at
FROM email_deliveries
ORDER BY created_at DESC
LIMIT 10;
```

## Assumptions
- 本阶段只做手动触发，不接定时任务。
- 如果当天没有 `hot_projects` 数据，邮件仍可生成，但内容会提示“请先执行热点计算”。
- 网易邮箱必须使用“授权码”，不是网页登录密码。
- 后续如果要自动每天 9 点发送，只需要复用 `EmailDigestService.run_digest()` 接入调度器。

