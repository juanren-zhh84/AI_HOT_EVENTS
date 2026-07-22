import logging
from collections.abc import Callable
from datetime import datetime, UTC
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Schedule
from app.db.session import SessionLocal
from app.schemas.discovery import DiscoveryRunRequest
from app.schemas.project_profile import ProjectProfileGenerateRequest
from app.services.discovery_service import DiscoveryService
from app.services.email_digest_service import EmailDigestService
from app.services.hot_project_service import HotProjectService
from app.services.project_profile_service import ProjectProfileService
from app.services.schedule_service import ScheduleService
from app.services.star_snapshot_service import StarSnapshotService

logger = logging.getLogger("uvicorn.error")  # 使用 uvicorn 日志器，方便在 PyCharm 和服务器日志中查看。
TaskRunner = Callable[[Session], dict | None]  # 每个调度任务都接收一个数据库 Session，并返回字典或 None。


class SchedulerService:  # 管理 APScheduler 的服务。
    """管理后台定时任务。"""  # 只负责调度，不直接实现业务逻辑。

    def __init__(self) -> None:  # 初始化调度服务。
        self.scheduler: BackgroundScheduler | None = None  # 延迟创建调度器，避免 import main.py 时就启动后台线程。
        self.timezone = ZoneInfo(settings.timezone)  # 使用配置里的默认时区。
        self.registered_count = 0  # 记录最近一次注册到 APScheduler 的任务数量。
        self.enabled_count = 0  # 记录数据库里最近一次启用的调度数量。

    def start(self) -> None:  # 启动调度器。
        if not settings.scheduler_enabled:  # 如果 .env 关闭了调度器。
            logger.info("调度器已关闭：SCHEDULER_ENABLED=false。")  # 记录关闭原因。
            return  # 直接返回，避免本地测试或调试时自动跑任务。
        if self.scheduler is not None and self.scheduler.running:  # 如果调度器已经在运行。
            logger.info("调度器已经在运行。")  # 记录重复启动。
            return  # 避免重复注册任务。
        self.scheduler = BackgroundScheduler(timezone=self.timezone)  # 创建后台调度器。
        self.registered_count = self._register_jobs()  # 从 schedules 表加载并注册任务。
        self.scheduler.start()  # 启动 APScheduler 后台线程。
        self._sync_next_run_times()  # 启动后同步每个任务的下一次运行时间。
        logger.info("调度器已启动，已注册任务数：%s。", self.registered_count)  # 输出启动日志。

    def stop(self) -> None:  # 停止调度器。
        if self.scheduler is None:  # 如果调度器还没初始化。
            logger.info("调度器未初始化。")  # 记录无需停止。
            return  # 直接返回。
        if self.scheduler.running:  # 如果调度器正在运行。
            self.scheduler.shutdown(wait=False)  # 不等待正在执行的任务结束，避免应用关闭卡住。
            logger.info("调度器已停止。")  # 输出停止日志。
        self.scheduler = None  # 清空引用，方便下次重新启动。
        self.registered_count = 0  # 清空注册数量。
        self.enabled_count = 0  # 清空启用调度数量。

    def reload(self) -> dict:  # 重新加载数据库里的调度规则。
        if not settings.scheduler_enabled:  # 如果调度器总开关关闭。
            return {"status": "disabled", "registered_count": 0, "enabled_count": 0}  # 返回关闭状态。
        if self.scheduler is None or not self.scheduler.running:  # 如果当前调度器没有运行。
            self.start()  # 直接启动调度器。
            return {"status": "started", "registered_count": self.registered_count, "enabled_count": self.enabled_count}  # 返回启动结果。
        self.scheduler.remove_all_jobs()  # 清空旧任务，避免旧 cron 继续生效。
        self.registered_count = self._register_jobs()  # 按数据库最新规则重新注册任务。
        self._sync_next_run_times()  # 同步下一次运行时间。
        return {"status": "reloaded", "registered_count": self.registered_count, "enabled_count": self.enabled_count}  # 返回重载结果。

    def _register_jobs(self) -> int:  # 注册所有启用调度。
        if self.scheduler is None:  # 如果调度器还没创建。
            raise RuntimeError("调度器未初始化。")  # 抛出内部错误，说明调用顺序不对。
        registered_count = 0  # 初始化注册数量。
        db = SessionLocal()  # 创建独立数据库会话。
        try:  # 确保数据库会话最终会关闭。
            service = ScheduleService(db)  # 创建调度配置服务。
            service.seed_default_schedules()  # 首次启动时写入默认调度，已有记录不覆盖。
            enabled_schedules = service.list_enabled_schedules()  # 查询数据库里启用的调度。
            self.enabled_count = len(enabled_schedules)  # 保存数据库启用调度数量，reload 接口需要返回它。
            for schedule in enabled_schedules:  # 遍历每条启用调度。
                if self._add_schedule_job(schedule):  # 尝试注册到 APScheduler。
                    registered_count += 1  # 注册成功数量加一。
            return registered_count  # 返回注册数量。
        finally:  # 不管注册是否成功都要关闭 Session。
            db.close()  # 关闭数据库会话。

    def _add_schedule_job(self, schedule: Schedule) -> bool:  # 把一条 Schedule 注册成 APScheduler job。
        if self.scheduler is None:  # 如果调度器还没创建。
            raise RuntimeError("调度器未初始化。")  # 抛出内部错误。
        runner = self._resolve_runner(schedule.name)  # 根据 schedule.name 找到对应业务函数。
        if runner is None:  # 如果没有匹配到业务函数。
            logger.warning("跳过未知调度：%s。", schedule.name)  # 记录跳过原因。
            return False  # 告诉调用方没有注册成功。
        trigger = CronTrigger.from_crontab(schedule.cron_expr, timezone=ZoneInfo(schedule.timezone))  # 把 cron_expr 转成触发器。
        self.scheduler.add_job(  # 注册 APScheduler job。
            func=lambda schedule_id=schedule.id, schedule_name=schedule.name, task_runner=runner: self._run_scheduled_job(schedule_id, schedule_name, task_runner),  # 到点后执行统一包装函数。
            trigger=trigger,  # 使用数据库里的 Cron 触发器。
            id=schedule.id,  # APScheduler job id 使用 schedules.id，方便 reload 时覆盖。
            name=schedule.name,  # APScheduler job name 使用业务名称，方便日志排查。
            replace_existing=True,  # 重复注册同名任务时覆盖旧任务，避免 reload 后冲突。
            max_instances=1,  # 同一个任务最多同时跑一个实例，避免任务重叠。
            coalesce=True,  # 服务短暂停顿错过多次触发时只补跑一次，避免任务堆积。
            misfire_grace_time=300,  # 错过触发时间 300 秒内允许补跑，超过则跳过。
        )  # add_job 调用结束。
        logger.info("已注册调度任务：%s，cron：%s。", schedule.name, schedule.cron_expr)  # 输出注册日志。
        return True  # 告诉调用方注册成功。

    def _resolve_runner(self, schedule_name: str) -> TaskRunner | None:  # 根据调度名称找到业务执行函数。
        runners: dict[str, TaskRunner] = {  # 调度名称到执行函数的映射。
            "repository_discovery": self._run_discovery,  # 自动发现 AI/Agent 仓库。
            "star_snapshot": self._run_star_snapshot,  # 采集星标快照。
            "profile_refresh": self._run_profile_refresh,  # 刷新项目画像。
            "hot_project_calculate": self._run_hot_project_calculate,  # 计算热点榜。
            "daily_digest": self._run_daily_digest,  # 发送邮件日报。
        }  # 映射结束。
        return runners.get(schedule_name)  # 返回匹配的函数，找不到返回 None。

    def _run_scheduled_job(self, schedule_id: str, schedule_name: str, runner: TaskRunner) -> None:  # 执行某个被调度的任务。
        self._run_with_session(  # 用统一方法创建 Session、记录日志和捕获异常。
            job_name=schedule_name,  # 日志里使用调度名称。
            runner=lambda db: self._run_and_touch_schedule(db, schedule_id, runner),  # 执行业务后更新 schedules 时间字段。
        )  # _run_with_session 调用结束。

    def _run_and_touch_schedule(self, db: Session, schedule_id: str, runner: TaskRunner) -> dict | None:  # 执行业务并更新调度运行时间。
        result = runner(db)  # 执行真正的业务任务，业务 service 会自己写 jobs 表。
        schedule = db.get(Schedule, schedule_id)  # 查询当前调度配置。
        if schedule is not None:  # 如果调度配置还存在。
            schedule.last_run_at = datetime.now(UTC)  # 记录最近一次实际运行时间。
            schedule.next_run_at = self._get_next_run_time(schedule_id)  # 记录 APScheduler 计算出的下一次运行时间。
            db.commit()  # 提交 schedules 时间字段。
        return result  # 返回业务结果，方便统一日志摘要。

    def _run_discovery(self, db: Session) -> dict:  # 执行自动发现任务。
        return DiscoveryService(db).run_discovery(DiscoveryRunRequest())  # 不指定 source_id 时执行全部启用监控源。

    def _run_star_snapshot(self, db: Session) -> dict:  # 执行星标快照任务。
        return StarSnapshotService(db).run_snapshot()  # 当前真实方法名是 run_snapshot，不是 collect_snapshots。

    def _run_profile_refresh(self, db: Session) -> dict:  # 执行项目画像刷新任务。
        return ProjectProfileService(db).run_profile_generation(ProjectProfileGenerateRequest(limit=100))  # 批量处理最多 100 个仓库。

    def _run_hot_project_calculate(self, db: Session) -> dict:  # 执行热点计算任务。
        return HotProjectService(db).calculate_hot_projects(report_date=None, top_n=settings.hot_project_top_n, include_disabled=False)  # 计算当天热点榜。

    def _run_daily_digest(self, db: Session) -> dict:  # 执行邮件日报任务。
        return EmailDigestService(db).run_digest(report_date=None, top_n=settings.hot_project_top_n, dry_run=False)  # 正式发送当天日报。

    def _run_with_session(self, job_name: str, runner: TaskRunner) -> None:  # 给定时任务提供独立数据库 Session。
        db = SessionLocal()  # 创建数据库会话。
        try:  # 捕获任务异常，避免后台线程崩溃。
            logger.info("%s 任务开始。", job_name)  # 记录任务开始。
            result = runner(db)  # 执行业务任务。
            logger.info("%s 任务结束：%s。", job_name, self._summarize_result(result))  # 记录任务摘要。
        except Exception:  # 捕获所有异常。
            db.rollback()  # 回滚当前未提交事务。
            logger.exception("%s 任务失败。", job_name)  # 打印完整异常堆栈。
        finally:  # 不管成功失败都关闭 Session。
            db.close()  # 关闭数据库会话。

    def _sync_next_run_times(self) -> None:  # 把 APScheduler 的下一次运行时间同步回 schedules 表。
        if self.scheduler is None:  # 如果调度器不存在。
            return  # 直接返回。
        db = SessionLocal()  # 创建数据库会话。
        try:  # 确保会话最终关闭。
            schedules = db.query(Schedule).all()  # 查询全部调度。
            for schedule in schedules:  # 遍历调度配置。
                schedule.next_run_at = self._get_next_run_time(schedule.id)  # 写入下一次运行时间，禁用任务会得到 None。
            db.commit()  # 提交 next_run_at。
        finally:  # 不管是否成功都关闭 Session。
            db.close()  # 关闭数据库会话。

    def _get_next_run_time(self, schedule_id: str):  # 查询 APScheduler 中某个 job 的下一次运行时间。
        if self.scheduler is None:  # 如果调度器不存在。
            return None  # 没有下一次运行时间。
        job = self.scheduler.get_job(schedule_id)  # 按 schedules.id 查询 APScheduler job。
        return job.next_run_time if job else None  # 找到 job 就返回 next_run_time，否则返回 None。

    def _summarize_result(self, result: dict | None) -> dict:  # 把业务返回值压缩成适合日志查看的小字典。
        if not isinstance(result, dict):  # 如果业务没有返回字典。
            return {}  # 返回空摘要。
        keys = (  # 只保留关键字段，避免日志打印大量 ORM 对象。
            "job_id",  # 任务 id。
            "status",  # 任务状态。
            "total",  # 快照或画像总数。
            "succeeded",  # 成功数量。
            "failed",  # 失败数量。
            "source_count",  # 自动发现监控源数量。
            "discovered_count",  # 自动发现候选数量。
            "inserted_count",  # 自动发现新增仓库数量。
            "updated_count",  # 自动发现更新仓库数量。
            "generated",  # 热点榜或画像生成数量。
            "report_id",  # 邮件日报 id。
            "subscriber_count",  # 邮件订阅者数量。
            "sent_count",  # 邮件发送成功数量。
            "failed_count",  # 邮件发送失败数量。
        )  # 关键字段定义结束。
        return {key: result.get(key) for key in keys if key in result}  # 只返回业务结果里实际存在的字段。


scheduler_service = SchedulerService()  # 暴露单例，main.py 生命周期和路由 reload 都使用它。