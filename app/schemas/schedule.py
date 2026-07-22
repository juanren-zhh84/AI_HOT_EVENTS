from datetime import datetime  # datetime 用于响应 last_run_at、next_run_at、created_at、updated_at。

from pydantic import BaseModel, Field  # BaseModel 定义响应模型，Field 定义字段校验和接口文档说明。


class ScheduleResponse(BaseModel):
    """调度配置响应体。"""
    id: str  # 调度主键，例如 schedule_daily_digest。
    name: str  # 调度名称，例如 daily_digest。
    cron_expr: str  # Cron 表达式，例如 0 9 * * *。
    timezone: str  # 调度时区，例如 Asia/Shanghai。
    enabled: bool  # 是否启用该调度。
    next_run_at: datetime | None = None  # 下一次运行时间，未注册或禁用时可以为空。
    last_run_at: datetime | None = None  # 最近一次运行时间，从未运行时为空。
    created_at: datetime  # 创建时间。
    updated_at: datetime  # 更新时间。

    model_config = {"from_attributes": True}  # 允许 Pydantic 直接从 SQLAlchemy ORM 对象读取字段。


class ScheduleUpdate(BaseModel):
    """调度配置更新请求体。"""

    cron_expr: str | None = Field(default=None, max_length=100, description="Cron 表达式，例如 0 9 * * *。")  # 不传表示不修改 Cron。
    timezone: str | None = Field(default=None, max_length=100, description="时区，例如 Asia/Shanghai。")  # 不传表示不修改时区。
    enabled: bool | None = Field(default=None, description="是否启用该调度。")  # 不传表示不修改启用状态。


class ScheduleReloadResponse(BaseModel):
    """调度重新加载响应体。""" 

    status: str  # 返回 reloaded、started、disabled 等状态。
    registered_count: int  # 本次注册到 APScheduler 的任务数量。
    enabled_count: int  # 数据库里启用的调度数量。