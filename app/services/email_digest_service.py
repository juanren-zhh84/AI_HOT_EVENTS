import smtplib  # Python 标准库 SMTP 客户端，用来真正发送邮件。
from datetime import UTC, date, datetime  # UTC 统一时间；date 表示日报日期；datetime 记录发送时间。
from email.message import EmailMessage  # 用来构造一封同时包含纯文本和 HTML 的邮件。
from sqlalchemy import select  # SQLAlchemy 2.x 推荐查询写法。
from sqlalchemy.orm import Session  # 数据库会话类型。
from app.core.config import settings  # 读取 SMTP、发件人等配置。
from app.db.models import EmailDelivery, EmailReport, HotProject, Subscriber  # 导入邮件、热点、订阅者 ORM 模型。

class EmailDigestService:
    """生成并发送Github热点项目日报"""
    def __init__(self,db: Session)->None:
        self.db = db

    def create_subscriber(self,email: str, name: str | None=None) -> Subscriber:
        """
        新增订阅者
        """
        existing = self.get_subscriber_by_email(email)
        if existing:
            return existing

        subscriber = Subscriber(email=email, name=name, status="active", preferences={})
        self.db.add(subscriber)
        self.db.commit()
        self.db.refresh(subscriber)
        return subscriber

    def get_subscriber_by_email(self, email: str) -> Subscriber | None:
        """
        根据邮件查订阅者
        """
        statement = select(Subscriber).where(Subscriber.email == email)
        return self.db.scalar(statement)

    def list_subscribers(self) -> list[Subscriber]:
        """查询订阅者列表"""
        statement = select(Subscriber).order_by(Subscriber.created_at.desc())
        return list(self.db.scalars(statement))

    def run_digest(self,report_date: date | None = None, top_n: int=20, dry_run: bool=False) -> dict:
        """手动生成/发送日报"""
        current_report_date = report_date or datetime.now(UTC).date()
        hot_projects = self._load_hot_projects(current_report_date, top_n) # 查询当天热点榜单
        subscribers = self._load_active_subscribers() # 查询活跃订阅者

        subject = f"Github热点项目日报 - {current_report_date.isoformat()}"  # 邮件标题
        html_content = self._build_html_content(current_report_date, hot_projects) # 生成HTML内容
        text_content = self._build_text_content(current_report_date, hot_projects) # 生成纯文本内容

        report = self._create_or_update_report(current_report_date, subject, html_content, text_content) # 保存或更新日报
        deliveries:list[EmailDelivery] = [] # 保存投递记录
        sent_count = 0
        failed_count = 0
        if dry_run: # 如果只是预演
            report.status = "draft" # 只生成报告，不进入发送状态
            self.db.commit()
            return self._build_response(report, [], 0, 0, True)
        report.status = "sending"
        self.db.commit()

        for subscriber in subscribers:
            delivery = self._prepare_delivery(report, subscriber)  # 先准备投递记录；已有记录就复用，避免重复插入触发唯一约束。

            try: # 单个订阅者失败不影响其他订阅者
                self._send_email(subscriber.email, subject, text_content, html_content) # 真正发送邮件
                delivery.status = "sent"
                delivery.sent_at = datetime.now(UTC)
                delivery.error_message = None
                sent_count += 1
            except Exception as exc:
                delivery.status = "failed"
                delivery.error_message = str(exc)
                failed_count += 1

            self.db.commit() # 提交当前订阅者投递结果
            self.db.refresh(delivery) # 刷新投递记录
            deliveries.append(delivery) # 加入返回列表

        report.status = "sent" if failed_count == 0 else "failed" # 全部成功才算sent，否则failed
        report.sent_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(report)

        return self._build_response(report, deliveries, sent_count, failed_count, False) # 返回接口响应

    def _load_hot_projects(self, report_date, top_n):
        """查询当前热点项目"""
        statement = (
            select(HotProject)
            .where(HotProject.report_date == report_date)
            .order_by(HotProject.rank_no.asc())
            .limit(top_n)
        )
        return list(self.db.scalars(statement).all())

    def _load_active_subscribers(self):
        """查询active订阅者"""
        statement = (
            select(Subscriber)
            .where(Subscriber.status == "active")
            .order_by(Subscriber.created_at.asc())
        )
        return list(self.db.scalars(statement).all())

    def _prepare_delivery(self, report: EmailReport, subscriber: Subscriber) -> EmailDelivery:
        """创建或复用某份日报对某个订阅者的投递记录。"""
        statement = (  # 构造查询语句，用来查“这份日报 + 这个订阅者”是否已经有投递记录。
            select(EmailDelivery)  # 查询 email_deliveries 表对应的 ORM 对象。
            .where(EmailDelivery.report_id == report.id)  # 同一份日报用 report_id 判断。
            .where(EmailDelivery.subscriber_id == subscriber.id)  # 同一个收件人用 subscriber_id 判断。
        )
        delivery = self.db.scalar(statement)  # 执行查询；查到返回旧记录，查不到返回 None。

        if delivery is None:  # 如果之前没有投递记录，说明这是第一次给这个订阅者发送这份日报。
            delivery = EmailDelivery(  # 创建新的投递记录，后面会写入 email_deliveries 表。
                report_id=report.id,  # 关联当前日报，保证知道这条投递属于哪份日报。
                subscriber_id=subscriber.id,  # 关联当前订阅者，保证知道这条投递发给谁。
                email=subscriber.email,  # 冗余保存邮箱地址，方便以后订阅者改邮箱后还能查历史。
                status="sending",  # 刚准备发送，所以先标记为 sending。
                retry_count=0,  # 第一次发送不是重试，所以重试次数从 0 开始。
            )
            self.db.add(delivery)  # 新对象必须加入 Session，commit 时才会真正写入数据库。
        else:  # 如果已经有投递记录，说明用户重复点击了同一天同一份日报的正式发送。
            delivery.email = subscriber.email  # 使用订阅者当前邮箱，避免历史邮箱和当前邮箱不一致。
            delivery.status = "sending"  # 重新发送前把状态改回 sending，表示本次正在处理。
            delivery.retry_count = (delivery.retry_count or 0) + 1  # 复用旧记录时记录重复发送次数，方便排查。
            delivery.error_message = None  # 清空上一次失败原因，避免本次还没失败就显示旧错误。
            delivery.sent_at = None  # 清空上一次发送时间，等本次真正成功后再写入新时间。

        self.db.commit()  # 提交新增或更新后的投递记录。
        self.db.refresh(delivery)  # 刷新对象，拿到数据库最终保存的状态。
        return delivery  # 返回投递记录，后续继续执行真正发邮件和状态更新。

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

    def _create_or_update_report(self, report_date, subject, html_content, text_content):
        """保存日报"""
        statement = select(EmailReport).where(EmailReport.report_date == report_date) # 同一天只允许一份日报
        report = self.db.scalar(statement) # 查询已有日报
        if report is None: # 如果没有就创建并加入数据库
            report = EmailReport(report_date=report_date, subject=subject, html_content=html_content, text_content=text_content, status="draft")
            self.db.add(report)
        else: # 否则更新
            report.subject = subject
            report.html_content = html_content
            report.text_content = text_content
            report.status = "draft" # 更新后想回到draft
        self.db.commit()
        self.db.refresh(report)
        return report

    def _build_response(self, report, deliveries, sent_count, failed_count, dry_run) -> dict:
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


    def _send_email(self, to_email, subject, text_content, html_content) -> None:
        """发送单个邮件"""
        if not settings.smtp_host:
            raise ValueError("SMTP_HOST 未配置。")
        if not settings.smtp_username:
            raise ValueError("SMTP_USERNAME 未配置。")
        if not settings.smtp_password:
            raise ValueError("SMTP_PASSWORD 未配置。")

        from_email = settings.mail_from or settings.smtp_username # 发件人邮箱，不配置 MAIL_FROM 时使用 SMTP_USERNAME。
        message = EmailMessage() # 创建邮箱对象
        message["Subject"] = subject
        message["From"] = f"{settings.mail_from_name} <{from_email}>"  # 发件人展示名。
        message["To"] = to_email  # 收件人。
        message.set_content(text_content)  # 设置纯文本内容，兼容不支持 HTML 的客户端。
        message.add_alternative(html_content, subtype="html")  # 添加 HTML 内容。

        if settings.smtp_use_ssl: # 465端口通常使用ssl
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=20) as smtp: # 建立ssl smtp连接
                smtp.login(settings.smtp_username, settings.smtp_password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp: # 建立普通SMTP连接
                if settings.smtp_use_tls:
                    smtp.starttls() # 587端口通常需要starttls
                smtp.login(settings.smtp_username, settings.smtp_password)
                smtp.send_message(message)



