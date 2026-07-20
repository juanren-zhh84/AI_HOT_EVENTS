from datetime import datetime

from pydantic import BaseModel, Field


class DiscoveryRunRequest(BaseModel):
    """自动发现请求体"""
    source_id: str|None = Field(default=None, description="指定监控源id；不传则执行全部启用监控源")
    max_pages: int = Field(default=1, ge=1, le=10, description="每个监控源最多拉去页数") # 限制页数，避免一次请求打爆Github限流
    per_page: int = Field(default=30, ge=1, le=100, description="每页数量")

class DiscoveryRunResponse(BaseModel):
    """自动发现任务响应体"""
    job_id: str  # jobs 表任务 id。
    status: str  # 任务状态。
    source_count: int  # 本次参与执行的监控源数量。
    discovered_count: int  # 从 GitHub 拉到的候选仓库数量。
    inserted_count: int  # 新增入库的仓库数量。
    updated_count: int  # 已存在但被更新的仓库数量。
    skipped_count: int  # 因过滤规则跳过的仓库数量。
    started_at: datetime | None = None  # 任务开始时间。
    finished_at: datetime | None = None  # 任务结束时间。