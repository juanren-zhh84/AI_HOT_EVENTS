from datetime import datetime

from pydantic import BaseModel, Field


class MonitorSourceCreate(BaseModel):
    """创建监控源请求体"""
    name: str = Field(..., description="监控源名称") # 例如“AI热门项目”
    source_type: str = Field(..., description="manual/github_search/topic/owner")
    query: str = Field(..., description="查询表达式")
    filters: dict = Field(default_factory=dict, description="过滤条件") # 保存 min_stars、keywords 等过滤条件。
    enabled: bool = Field(default=True, description="是否启用")
    discover_interval_minutes: int = Field(default=360, ge=1) # 发现间隔，最小1分钟

class MonitorSourceUpdate(BaseModel):
    """更新监控资源请求体"""
    name: str | None = Field(default=None, description="监控源名称")
    source_type: str | None = Field(default=None, description="manual/github_search/topic/owner") # 不传则表示不修改类型
    query: str | None = Field(default=None, description="查询表达式")
    filters: dict | None = Field(default=None, description="过滤条件")
    enabled: bool | None = Field(default=None, description="是否启用")
    discover_interval_minutes: int = Field(default=360, ge=1)

class MonitorSourceResponse(BaseModel):
    """监控源响应体"""
    id: str
    name: str
    source_type: str
    query: str
    filters: dict
    enabled: bool
    discover_interval_minutes: int
    last_discovered_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
