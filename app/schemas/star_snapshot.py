from datetime import datetime

from pydantic import BaseModel,Field


class StarSnapshotRunRequest(BaseModel):
    """手动触发星标快照采集的请求体"""
    repository_ids: list[str] | None = Field(
        default=None,
        description = "指定仓库id列表；不传则采集所有的enabled=true的仓库"
    )

    include_disabled: bool = Field(
        default=False,
        description="是否采集已暂停的仓库，默认False"
    )


class StarSnapshotError(BaseModel):
    """单个仓库采集失败时的错误信息"""
    repository_id: str | None = None
    full_name: str | None = None
    error_message: str # 失败信息，比如github 404、限流等

class StarSnapshotResponse(BaseModel):
    """星标快照响应体"""
    id: str
    repository_id: str
    stars: int
    forks: int
    watchers: int
    open_issues: int
    source: str
    snapshot_at: datetime
    created_at: datetime

class StarSnapshotRunResponse(BaseModel):
    """手动采集任务的整体响应体"""
    job_id: str  # jobs 表里的任务 id，方便后续排查本次执行。
    status: str  # 任务状态：succeeded 或 failed。
    total: int  # 本次计划采集的仓库数量。
    succeeded: int  # 本次成功采集的仓库数量。
    failed: int  # 本次失败的仓库数量。
    snapshots: list[StarSnapshotResponse]  # 本次成功写入的快照列表。
    errors: list[StarSnapshotError]  # 本次失败的仓库错误列表。