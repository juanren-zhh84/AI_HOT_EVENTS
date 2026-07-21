from datetime import datetime

from pydantic import BaseModel, Field

"""
项目画像:
负责把仓库从“指标列表”变成“人能快速理解的项目介绍”。它会优先读 README，README 缺失时降级到 GitHub description。
"""
class ProjectProfileGenerateRequest(BaseModel):
    """项目画像生成请求体"""
    repository_id: str|None = Field(default=None,description="指定仓库id，不传则处理缺少画像的仓库")
    limit: int = Field(default=20, ge=10, le=100, description="批量处理数量")
    force: bool = Field(default=False,description="是否强制重新生成")

class ProjectProfileResponse(BaseModel):
    """项目画像响应体"""
    id: str  # project_profiles 表主键。
    repository_id: str  # 对应 repositories.id。
    summary: str | None = None  # 一句话简介。
    features: list[str]  # 功能点。
    audience: list[str]  # 适用人群。
    highlights: list[str]  # 项目亮点。
    tech_stack: dict  # 技术栈识别结果。
    readme_hash: str | None = None  # README 哈希。
    summary_status: str  # complete、partial、failed。
    generated_at: datetime | None = None  # 生成时间。
    created_at: datetime  # 创建时间。
    updated_at: datetime  # 更新时间。

    model_config = {"from_attributes": True}  # 允许从 ORM 对象直接转换。