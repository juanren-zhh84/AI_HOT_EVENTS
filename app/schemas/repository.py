from datetime import datetime
from pydantic import BaseModel,Field

class RepositoryCreate(BaseModel):
    """
    创建仓库时的请求体模型。

    为什么需要这个类？
    FastAPI 会用它自动校验请求参数。
    比如 full_name 必须传，tags 必须是列表。
    """
    full_name: str = Field(
        ..., # ... 表示必填；不传时 FastAPI 会自动返回 422。
        examples=["openai/openai-python"],
        description="GitHub 仓库完整名称，格式必须是 owner/repo",
    )
    source: str = Field(default="manual",description="仓库来源，默认手动添加")
    tags: list[str] = Field(default_factory=list,description="本地标签") # tags 用 default_factory，避免多个请求共享同一个列表
    enabled: bool = Field(default=True,description="是否启用监控")


class RepositoryUpdate(BaseModel):
    """
    更新仓库接口的请求体模型。
    """
    enabled:bool | None = Field(default=None,description="是否启用监控")
    tags:list[str] | None = Field(default=None,description="本地标签") # 不传 tags 表示保留原标签。



class RepositoryResponse(BaseModel):
    """响应体"""
    id: str  # 仓库在本系统数据库里的 UUID。
    owner: str  # GitHub owner，例如 openai。
    name: str  # GitHub 仓库名，例如 openai-python。
    full_name: str  # GitHub 完整仓库名，例如 openai/openai-python。
    html_url: str  # GitHub 页面地址。
    homepage: str | None = None  # 项目主页，可能为空。
    description: str | None = None  # 仓库描述，可能为空。
    primary_language: str | None = None  # 主语言，可能为空。
    topics: list[str]  # GitHub topics，统一返回列表。
    license_name: str | None = None  # 许可证名称，可能为空。
    stars: int  # 当前 stars 数。
    forks: int  # 当前 forks 数。
    watchers: int  # 当前 watchers 数。
    open_issues: int  # 当前 open issues 数。
    archived: bool  # 是否归档。
    disabled: bool  # 是否被禁用。
    enabled: bool  # 本系统是否启用监控。
    source: str  # 来源，例如 manual。
    tags: list[str]  # 本地标签。
    github_created_at: datetime | None = None  # GitHub 创建时间。
    github_updated_at: datetime | None = None  # GitHub 更新时间。
    last_pushed_at: datetime | None = None  # 最近 push 时间。
    last_collected_at: datetime | None = None  # 本系统最近采集时间。

    model_config = {"from_attributes": True}  # 允许从 SQLAlchemy ORM 对象直接生成响应模型。












