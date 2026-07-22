from datetime import datetime

from pydantic import BaseModel


class JobResponse(BaseModel):  # 后台任务响应体。
    """后台任务响应体。"""  # jobs 表记录某一次任务执行结果。

    id: str  # jobs 表主键。
    job_type: str  # 任务类型，例如 discovery、profile_refresh、email_digest。
    status: str  # 任务状态，例如 pending、running、succeeded、failed。
    payload: dict  # 任务参数，例如本次采集的仓库 id 列表。
    progress: dict  # 任务进度，例如 total、succeeded、failed。
    error_message: str | None = None  # 失败原因，成功时为空。
    started_at: datetime | None = None  # 任务开始时间。
    finished_at: datetime | None = None  # 任务结束时间。
    created_at: datetime  # 创建时间。
    updated_at: datetime  # 更新时间。

    model_config = {"from_attributes": True}  # 允许从 SQLAlchemy ORM 对象直接转换。