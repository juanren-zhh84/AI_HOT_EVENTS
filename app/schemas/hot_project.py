from datetime import date, datetime

from pydantic import BaseModel,Field


class HotProjectCalculateRequest(BaseModel):
    """
    手动触发热电项目计算的请求体
    """
    report_date: date | None = Field(
        default=None,
        description="榜单日期，不传则使用当前日期"
    )
    top_n: int = Field(
        default=20,
        ge=1,
        le=100,
        description="生成热点项目数量，范围1-100"
    )
    include_disabled: bool = Field(
        default=False,
        description="是否包含enabled=true的仓库"
    )

class HotProjectResponse(BaseModel):
    """热点项目响应体"""
    id: str  # hot_projects 表主键。
    repository_id: str  # 仓库 id。
    full_name: str  # 仓库完整名，例如 openai/openai-python。
    html_url: str  # GitHub 页面地址。
    description: str | None = None  # 仓库描述，可能为空。
    primary_language: str | None = None  # 主语言，可能为空。
    report_date: date  # 榜单日期。
    rank_no: int  # 排名。
    hot_score: float  # 热度分。
    stars: int  # 当前总 star 数。
    stars_delta_24h: int  # 近 24 小时新增 star。
    stars_delta_7d: int  # 近 7 天新增 star。
    growth_rate_24h: float  # 24 小时增长率。
    reason: str | None = None  # 入选原因。
    created_at: datetime  # 创建时间。
    updated_at: datetime  # 更新时间。



class HotProjectRunResponse(BaseModel):
    """
    热点计算任务响应体
    """
    job_id: str  # jobs 表任务 id。
    status: str  # 任务状态。
    report_date: date  # 本次计算的榜单日期。
    total_candidates: int  # 参与计算的候选仓库数量。
    generated: int  # 最终写入 hot_projects 的数量。
    hot_projects: list[HotProjectResponse]  # 本次生成的热点项目列表。



