from zoneinfo import ZoneInfo

from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.db.models import Schedule
from app.schemas.schedule import ScheduleUpdate

DEFAULT_SCHEDULES = (  # 默认调度列表，用于首次初始化 schedules 表。
    ("schedule_discovery", "repository_discovery", "discovery_cron"),  # 自动发现 AI/Agent 仓库。
    ("schedule_star_snapshot", "star_snapshot", "star_snapshot_cron"),  # 采集星标快照。
    ("schedule_profile_refresh", "profile_refresh", "profile_refresh_cron"),  # 刷新项目画像。
    ("schedule_hot_project_calculate", "hot_project_calculate", "hot_project_cron"),  # 计算热点榜。
    ("schedule_daily_digest", "daily_digest", "digest_cron"),  # 发送邮件日报。
)  # 元组结束。


class ScheduleService:
    def __init__(self, db):
        self.db = db

    def seed_default_schedules(self):
        created = False
        for schedule_id, schedule_name, setting_name in DEFAULT_SCHEDULES:  # 遍历默认调度定义。
            schedule = self.db.get(Schedule, schedule_id)  # 按主键查询调度是否已经存在。
            if schedule is not None:  # 如果数据库已经有这条调度。
                continue  # 不覆盖管理员已经修改过的 cron。
            cron_expr = getattr(settings, setting_name)  # 从 settings 读取默认 cron。
            schedule = Schedule(  # 创建新的调度配置。
                id=schedule_id,  # 保存稳定主键，方便接口按 id 管理。
                name=schedule_name,  # 保存调度名称，SchedulerService 用它映射执行函数。
                cron_expr=cron_expr,  # 使用 .env 里的默认 cron 初始化。
                timezone=settings.timezone,  # 使用 .env 里的默认时区初始化。
                enabled=True,  # 默认启用，保证服务启动后能自动跑。
            )  # Schedule 构造结束。
            self.db.add(schedule)  # 加入数据库会话。
            created = True  # 标记本次创建过默认调度。
        if created:  # 如果确实新增了默认调度。
            self.db.commit()  # 提交新增调度。
        return self.list_schedules()  # 返回当前全部调度，方便 SchedulerService 继续注册。

    def list_schedules(self) -> list[Schedule]:  # 查询全部调度配置。
        return self.db.query(Schedule).order_by(Schedule.id.asc()).all()  # 按 id 排序，保证返回顺序稳定。

    def list_enabled_schedules(self) -> list[Schedule]:  # 查询启用的调度配置。
        return self.db.query(Schedule).filter(Schedule.enabled.is_(True)).order_by(
            Schedule.id.asc()).all()  # 只返回 enabled=true。

    def get_schedule(self, schedule_id: str) -> Schedule | None:  # 查询单个调度配置。
        return self.db.get(Schedule, schedule_id)  # 按主键查询，查不到返回 None。

    def update_schedule(self, schedule_id: str, payload: ScheduleUpdate) -> Schedule | None:  # 更新调度配置。
        schedule = self.get_schedule(schedule_id)  # 先查调度是否存在。
        if schedule is None:  # 如果调度不存在。
            return None  # 交给路由返回 404。
        data = payload.model_dump(exclude_unset=True)  # 只取请求体里实际传入的字段。
        if "cron_expr" in data and data["cron_expr"] is not None:  # 如果管理员要修改 Cron。
            self._validate_cron_expr(data["cron_expr"], data.get("timezone") or schedule.timezone)  # 保存前先校验 Cron。
            schedule.cron_expr = data["cron_expr"]  # 写入新的 Cron 表达式。
        if "timezone" in data and data["timezone"] is not None:  # 如果管理员要修改时区。
            self._validate_timezone(data["timezone"])  # 保存前先校验时区。
            schedule.timezone = data["timezone"]  # 写入新的时区。
        if "enabled" in data and data["enabled"] is not None:  # 如果管理员要修改启用状态。
            schedule.enabled = data["enabled"]  # 写入启用或禁用状态。
        self.db.commit()  # 提交更新。
        self.db.refresh(schedule)  # 刷新 ORM 对象，确保响应返回最新值。
        return schedule  # 返回更新后的调度。

    def enable_schedule(self, schedule_id: str) -> Schedule | None:  # 启用调度。
        schedule = self.get_schedule(schedule_id)  # 查询调度。
        if schedule is None:  # 如果调度不存在。
            return None  # 交给路由返回 404。
        schedule.enabled = True  # 标记启用。
        self.db.commit()  # 提交启用状态。
        self.db.refresh(schedule)  # 刷新 ORM 对象。
        return schedule  # 返回启用后的调度。

    def disable_schedule(self, schedule_id: str) -> Schedule | None:  # 禁用调度。
        schedule = self.get_schedule(schedule_id)  # 查询调度。
        if schedule is None:  # 如果调度不存在。
            return None  # 交给路由返回 404。
        schedule.enabled = False  # 标记禁用。
        self.db.commit()  # 提交禁用状态。
        self.db.refresh(schedule)  # 刷新 ORM 对象。
        return schedule  # 返回禁用后的调度。

    def _validate_cron_expr(self, cron_expr: str, timezone: str) -> None:  # 校验 Cron 表达式。
        CronTrigger.from_crontab(cron_expr, timezone=ZoneInfo(timezone))  # APScheduler 能解析才允许保存。

    def _validate_timezone(self, timezone: str) -> None:  # 校验时区名称。
        ZoneInfo(timezone)  # Python 能加载该时区才允许保存。