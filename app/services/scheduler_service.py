import logging  # Python 标准日志库，用来记录调度器启动、停止、任务成功、任务失败。
from collections.abc import Callable  # 用来给“接收数据库 Session 的函数”做类型标注。
from zoneinfo import ZoneInfo  # Python 标准库时区工具，用来让 cron 按 Asia/Shanghai 运行。
from apscheduler.schedulers.background import BackgroundScheduler  # APScheduler 3.x 后台调度器，不阻塞 FastAPI 主线程。
from apscheduler.triggers.cron import CronTrigger  # cron 触发器，支持 0 9 * * * 这种表达式。
from app.core.config import settings  # 读取 .env 里的 cron、时区、开关等配置。
from app.db.session import SessionLocal  # 定时任务不是 HTTP 请求，所以要自己创建数据库 Session。
from app.services.email_digest_service import EmailDigestService  # 邮件日报服务。
from app.services.hot_project_service import HotProjectService  # 热点项目计算服务。
from app.services.star_snapshot_service import StarSnapshotService  # 星标快照采集服务。

logger = logging.getLogger("uvicorn.error")  # 使用 uvicorn 的日志器，保证启动服务时能在 PyCharm/终端看到调度日志。

class SchedulerService:
    """管理后台定时任务"""
    def __init__(self):
        self.scheduler: BackgroundScheduler | None = None
        self.timezone = ZoneInfo(settings.timezone)

    def start(self) -> None:
        """启动调度器"""
        if not settings.scheduler_enabled:
            logger.info("调度器已关闭：SCHEDULER_ENABLED=false。")
            return

        if self.scheduler is not None and self.scheduler.running:
            logger.info("调度器已经在运行。")
            return
        self.scheduler = BackgroundScheduler(timezone=self.timezone) # 创建后台调度器，后台线程执行任务
        self._register_jobs() # 注册星标快照、热点计算、邮件日报三个任务
        self.scheduler.start()
        logger.info("调度器已启动。")

    def stop(self) -> None:
        """停止调度"""
        if self.scheduler is None:
            logger.info("调度器未初始化。")
            return

        if self.scheduler.running:
            self.scheduler.shutdown(wait=False) # wait=false表示不等待正在执行的任务结束
            logger.info("调度器已停止。")

        self.scheduler = None # 清空引用，避免服务下次启动是复用已关闭的调度器


    def _register_jobs(self):
        """注册所有后台任务"""
        # 注册星标快照采集任务。
        self._add_cron_job(
            job_id = "star_snapshot_job",
            cron_expression = settings.star_snapshot_cron,
            job_func = self._run_star_snapshot_job,
        )

        # 注册热点项目计算任务
        self._add_cron_job(
            job_id = "hot_project_job",
            cron_expression = settings.hot_project_cron,
            job_func = self._run_hot_project_job,
        )

        # 注册邮件日报发送任务
        self._add_cron_job(  # 注册邮件日报发送任务。
            job_id="email_digest_job",  # 任务 id。
            cron_expression=settings.digest_cron,  # 从 .env 读取邮件日报 cron。
            job_func=self._run_email_digest_job,  # 到点后执行这个函数。
        )

    def _add_cron_job(self, job_id, cron_expression, job_func):
        if self.scheduler is None:
            raise RuntimeError("调度器未初始化") # 理论上这里已经创建scheduler，这里防御一下

        trigger = CronTrigger.from_crontab(cron_expression, timezone=self.timezone) # 把 0 9 * * * 转成 APScheduler 触发器
        # 把任务交给 APScheduler 管理。
        self.scheduler.add_job(
            func=job_func,
            trigger=trigger,
            id=job_id,
            name=job_id,
            replace_existing=True,  # 重复注册同名任务时覆盖旧任务，避免 reload 后重复。
            max_instances=1,  # 同一个任务最多同时跑 1 个，避免上一次没跑完下一次又开始。
            coalesce=True,  # 如果服务短暂停顿错过多次触发，只补跑一次，避免任务堆积。
            misfire_grace_time=300,  # 错过触发时间 300 秒内仍允许执行，超过就跳过。
        )
        logger.info("已注册调度任务：%s，cron：%s。", job_id, cron_expression)

    def _run_star_snapshot_job(self) -> None:
        """执行星标快照采集任务。"""
        self._run_with_session(  # 用统一方法创建和关闭数据库 Session。
            job_name="star_snapshot_job",
            runner=lambda db: StarSnapshotService(db).run_snapshot(),  # 创建服务并采集所有启用仓库。
        )

    def _run_hot_project_job(self) -> None:
        """执行热点计算任务"""
        self._run_with_session(
            job_name="hot_project_job",
            runner=lambda db: HotProjectService(db).calculate_hot_projects(
                report_date=None,
                top_n=settings.hot_project_top_n,
                include_disabled=False,
            ),
        )

    def _run_email_digest_job(self) -> None:
        """执行邮件发送任务"""
        self._run_with_session(
            job_name="email_digest_job",
            runner=lambda db:EmailDigestService(db).run_digest(
                report_date=None,
                top_n=settings.hot_project_top_n,
                dry_run=False,
            ),
        )



    def _run_with_session(self, job_name, runner):
        """给定时任务提供数据库session"""
        db = SessionLocal()
        try:
            logger.info("%s 任务开始.",job_name)
            result = runner(db)
            logger.info("%s 任务结束：%s",job_name, self._summarize_result(result))
        except Exception:
            logger.exception("%s 任务失败.",job_name)
        finally:
            db.close()

    def _summarize_result(self, result):
        """把业务返回值压缩成适合日志查看的小字典"""
        keys = (  # 只保留这些关键字段，避免日志打印大量 ORM 对象。
            "job_id",  # 任务 id。
            "status",  # 任务状态。
            "total",  # 快照采集总数。
            "succeeded",  # 快照采集成功数。
            "failed",  # 快照采集失败数。
            "total_candidates",  # 热点候选数量。
            "generated",  # 生成热点数量。
            "report_id",  # 邮件日报 id。
            "subscriber_count",  # 收件人数量。
            "sent_count",  # 发送成功数量。
            "failed_count",  # 发送失败数量。
        )
        return {key: result.get(key) for key in keys if key in result}  # 只返回实际存在的字段。

scheduler_service = SchedulerService()
