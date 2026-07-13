```python

from datetime import datetime  # datetime 用来声明接口返回里的时间字段类型。

from pydantic import BaseModel, Field  # BaseModel 是 Pydantic 模型基类，Field 用来定义默认值、示例和字段说明。


class RepositoryCreate(BaseModel):  # 创建仓库接口的请求体模型。
    full_name: str = Field(  # full_name 表示 GitHub 仓库完整名。
        ...,  # ... 表示必填；不传时 FastAPI 会自动返回 422。
        examples=["openai/openai-python"],  # 在 /docs 里显示示例，方便手动测试。
        description="GitHub 仓库完整名称，格式必须是 owner/repo",  # 字段说明会进入 OpenAPI 文档。
    )
    source: str = Field(default="manual", description="仓库来源，默认手动添加")  # source 标记仓库来源，当前先默认 manual。
    tags: list[str] = Field(default_factory=list, description="本地标签")  # tags 用 default_factory，避免多个请求共享同一个列表。
    enabled: bool = Field(default=True, description="是否启用监控")  # enabled 控制添加后是否参与后续采集。


class RepositoryUpdate(BaseModel):  # 更新仓库接口的请求体模型。
    enabled: bool | None = Field(default=None, description="是否启用监控")  # PATCH 是局部更新，不传就不修改。
    tags: list[str] | None = Field(default=None, description="本地标签")  # 不传 tags 表示保留原标签。


class RepositoryResponse(BaseModel):  # 仓库接口统一响应模型。
    id: str  # 本系统数据库里的仓库 UUID。
    owner: str  # GitHub owner，例如 openai。
    name: str  # GitHub 仓库名，例如 openai-python。
    full_name: str  # GitHub 完整仓库名，例如 openai/openai-python。
    html_url: str  # GitHub 仓库页面地址。
    homepage: str | None = None  # 项目主页，可能为空。
    description: str | None = None  # 仓库描述，可能为空。
    primary_language: str | None = None  # 主语言，可能为空。
    topics: list[str]  # GitHub topics。
    license_name: str | None = None  # 许可证名称，可能为空。
    stars: int  # 当前 stars 数。
    forks: int  # 当前 forks 数。
    watchers: int  # 当前 watchers 数。
    open_issues: int  # 当前 open issues 数。
    archived: bool  # 是否归档。
    disabled: bool  # 是否被 GitHub 禁用。
    enabled: bool  # 本系统是否启用监控。
    source: str  # 仓库来源。
    tags: list[str]  # 本地标签。
    github_created_at: datetime | None = None  # GitHub 创建时间。
    github_updated_at: datetime | None = None  # GitHub 更新时间。
    last_pushed_at: datetime | None = None  # 最近 push 时间。
    last_collected_at: datetime | None = None  # 本系统最近采集时间。

    model_config = {"from_attributes": True}  # 允许从 SQLAlchemy ORM 对象直接生成响应模型。
```

### 2. Service 层
新增 `app/services/repository_service.py`，只放业务逻辑：

```python
# app/services/repository_service.py  # 这个文件只处理业务，不直接定义 HTTP 接口。

from datetime import UTC, datetime  # UTC 用来统一保存时间；datetime 用来转换 GitHub 时间字符串。

import httpx  # 用来捕获 GitHubClient 请求 GitHub 时抛出的 HTTP 错误。
from sqlalchemy import select  # SQLAlchemy 2.x 推荐用 select 构造查询。
from sqlalchemy.orm import Session  # Session 是数据库会话类型。

from app.db.models import Repository  # Repository 是 repositories 表的 ORM 模型。
from app.services.github_client import GitHubClient  # GitHubClient 负责访问 GitHub API。


def parse_github_datetime(value: str | None) -> datetime | None:  # 把 GitHub 时间字符串转成 datetime。
    if not value:  # GitHub 某些时间字段可能为空。
        return None  # 为空时直接返回 None，数据库也保存为空。
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)  # GitHub 的 Z 表示 UTC，这里转成 Python datetime。


class RepositoryService:  # 仓库业务服务。
    def __init__(self, db: Session) -> None:  # 初始化时传入数据库会话。
        self.db = db  # 保存数据库会话，后面查询、插入、更新都用它。
        self.github_client = GitHubClient()  # 创建 GitHub 客户端，后面拉取仓库详情。

    def create_repository(self, full_name: str, source: str = "manual", tags: list[str] | None = None, enabled: bool = True) -> Repository:  # 创建仓库。
        owner, repo = self._parse_full_name(full_name)  # 校验并拆分 owner/repo。

        existing_repository = self.get_by_full_name(full_name)  # 先查重，避免重复插入。
        if existing_repository:  # 如果数据库里已经存在。
            return existing_repository  # 直接返回已有记录，让接口具备幂等性。

        try:  # 请求 GitHub 可能失败。
            github_data = self.github_client.get_repository(owner, repo)  # 获取 GitHub 仓库详情。
        except httpx.HTTPStatusError as exc:  # 捕获 GitHub 返回的 4xx/5xx。
            if exc.response.status_code == 404:  # 404 表示仓库不存在。
                raise ValueError(f"GitHub repository not found: {full_name}") from exc  # 转成业务错误，交给路由返回 400。
            raise  # 其他错误暂时继续抛出，后续再统一处理。

        repository = Repository(  # 把 GitHub 返回数据转换成 ORM 对象。
            owner=github_data["owner"]["login"],  # GitHub owner.login -> repositories.owner。
            name=github_data["name"],  # GitHub name -> repositories.name。
            full_name=github_data["full_name"],  # GitHub full_name -> repositories.full_name。
            html_url=github_data["html_url"],  # GitHub html_url -> repositories.html_url。
            homepage=github_data.get("homepage"),  # homepage 可能为空，用 get 更安全。
            description=github_data.get("description"),  # description 可能为空。
            primary_language=github_data.get("language"),  # language 可能为空。
            topics=github_data.get("topics") or [],  # topics 为空时保存空列表。
            license_name=(github_data.get("license") or {}).get("name"),  # license 可能是 None，所以先 or {}。
            stars=github_data.get("stargazers_count") or 0,  # stars 为空时保存 0。
            forks=github_data.get("forks_count") or 0,  # forks 为空时保存 0。
            watchers=github_data.get("watchers_count") or 0,  # watchers 为空时保存 0。
            open_issues=github_data.get("open_issues_count") or 0,  # open issues 为空时保存 0。
            archived=github_data.get("archived") or False,  # archived 为空时保存 False。
            disabled=github_data.get("disabled") or False,  # disabled 为空时保存 False。
            enabled=enabled,  # 使用请求体里的 enabled。
            source=source,  # 使用请求体里的 source。
            tags=tags or [],  # tags 不传时保存空列表。
            github_created_at=parse_github_datetime(github_data.get("created_at")),  # 转换 GitHub 创建时间。
            github_updated_at=parse_github_datetime(github_data.get("updated_at")),  # 转换 GitHub 更新时间。
            last_pushed_at=parse_github_datetime(github_data.get("pushed_at")),  # 转换最近 push 时间。
            last_collected_at=datetime.now(UTC),  # 记录本系统本次采集时间。
        )

        self.db.add(repository)  # 把 ORM 对象加入 Session。
        self.db.commit()  # 提交事务，真正写入 MySQL。
        self.db.refresh(repository)  # 刷新对象，拿到数据库最终状态。
        return repository  # 返回创建后的仓库对象。

    def list_repositories(self) -> list[Repository]:  # 查询仓库列表。
        statement = select(Repository).order_by(Repository.created_at.desc())  # 按创建时间倒序。
        return list(self.db.scalars(statement).all())  # 返回 ORM 对象列表。

    def get_repository(self, repository_id: str) -> Repository | None:  # 根据 id 查仓库。
        return self.db.get(Repository, repository_id)  # 主键查询，查不到返回 None。

    def get_by_full_name(self, full_name: str) -> Repository | None:  # 根据 owner/repo 查仓库。
        statement = select(Repository).where(Repository.full_name == full_name)  # 构造 full_name 查询条件。
        return self.db.scalar(statement)  # 查到返回对象，查不到返回 None。

    def update_repository(self, repository_id: str, enabled: bool | None = None, tags: list[str] | None = None) -> Repository | None:  # 更新仓库配置。
        repository = self.get_repository(repository_id)  # 先查仓库是否存在。
        if not repository:  # 如果仓库不存在。
            return None  # 交给路由层返回 404。

        if enabled is not None:  # enabled 不为 None 才更新。
            repository.enabled = enabled  # 修改启停状态。

        if tags is not None:  # tags 不为 None 才更新。
            repository.tags = tags  # 修改本地标签。

        self.db.commit()  # 提交修改。
        self.db.refresh(repository)  # 刷新对象。
        return repository  # 返回更新后的仓库。

    def _parse_full_name(self, full_name: str) -> tuple[str, str]:  # 校验并拆分 owner/repo。
        parts = full_name.strip().split("/")  # 去掉两端空格后按 / 拆分。
        if len(parts) != 2 or not parts[0] or not parts[1]:  # 必须正好两段且都非空。
            raise ValueError("full_name must be in owner/repo format")  # 格式错误时抛业务异常。
        return parts[0], parts[1]  # 返回 owner 和 repo。
```

### 3. Router 层
新增 `app/api/routes_repositories.py`，只放接口定义：

```python
# app/api/routes_repositories.py  # 这个文件只定义 HTTP 接口，不直接写复杂业务。

from fastapi import APIRouter, Depends, HTTPException, status  # APIRouter 定义路由，Depends 注入依赖，HTTPException 返回错误。
from sqlalchemy.orm import Session  # Session 用于类型标注数据库会话。

from app.db.session import get_db  # get_db 为每个请求提供数据库会话。
from app.schemas.repository import RepositoryCreate, RepositoryResponse, RepositoryUpdate  # 导入请求体和响应体模型。
from app.services.repository_service import RepositoryService  # 导入仓库业务服务。


router = APIRouter(prefix="/repositories", tags=["repositories"])  # 当前文件所有接口统一以 /repositories 开头。


@router.post("", response_model=RepositoryResponse, status_code=status.HTTP_201_CREATED)  # POST /repositories 创建仓库。
def create_repository(payload: RepositoryCreate, db: Session = Depends(get_db)) -> RepositoryResponse:  # 接收请求体和数据库会话。
    service = RepositoryService(db)  # 创建业务服务。
    try:  # 创建仓库可能出现业务错误。
        return service.create_repository(payload.full_name, payload.source, payload.tags, payload.enabled)  # 调用 service 完成创建。
    except ValueError as exc:  # 捕获 full_name 格式错误或 GitHub 404。
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc  # 转成 HTTP 400。


@router.get("", response_model=list[RepositoryResponse])  # GET /repositories 查询列表。
def list_repositories(db: Session = Depends(get_db)) -> list[RepositoryResponse]:  # 注入数据库会话。
    service = RepositoryService(db)  # 创建业务服务。
    return service.list_repositories()  # 返回仓库列表。


@router.get("/{repository_id}", response_model=RepositoryResponse)  # GET /repositories/{repository_id} 查询详情。
def get_repository(repository_id: str, db: Session = Depends(get_db)) -> RepositoryResponse:  # 接收路径参数和数据库会话。
    service = RepositoryService(db)  # 创建业务服务。
    repository = service.get_repository(repository_id)  # 查询仓库。
    if not repository:  # 查不到时。
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")  # 返回 404。
    return repository  # 返回仓库对象。


@router.patch("/{repository_id}", response_model=RepositoryResponse)  # PATCH /repositories/{repository_id} 更新配置。
def update_repository(repository_id: str, payload: RepositoryUpdate, db: Session = Depends(get_db)) -> RepositoryResponse:  # 接收路径参数、请求体和数据库会话。
    service = RepositoryService(db)  # 创建业务服务。
    repository = service.update_repository(repository_id, payload.enabled, payload.tags)  # 更新仓库配置。
    if not repository:  # 查不到时。
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")  # 返回 404。
    return repository  # 返回更新后的仓库对象。
```

### 4. 应用入口
修改 `app/main.py`，只增加仓库路由注册，不动健康检查逻辑：

```python
from fastapi import FastAPI  # FastAPI 是应用入口类。

from app.api.routes_health import router as health_router  # 健康检查路由。
from app.api.routes_repositories import router as repositories_router  # 仓库管理路由。
from app.core.config import settings  # 应用配置。


app = FastAPI(  # 创建 FastAPI 应用。
    title=settings.app_name,  # 应用名称。
    version=settings.app_version,  # 应用版本。
    docs_url="/docs",  # Swagger 文档地址。
    openapi_url="/openapi.json",  # OpenAPI JSON 地址。
)

app.include_router(health_router, prefix="/api/v1")  # 注册健康检查接口。
app.include_router(repositories_router, prefix="/api/v1")  # 注册仓库接口。


@app.get("/", include_in_schema=False)  # 根路径接口，不放进接口文档。
def root() -> dict[str, str]:  # 返回服务基础信息。
    return {  # 返回一个简单字典。
        "service": settings.app_name,  # 服务名称。
        "docs": "/docs",  # 文档地址。
        "health": "/api/v1/health",  # 健康检查地址。
    }
```

## Test Plan
- 确认 `httpx` 在依赖里；当前 `requirements.txt` 没有，需要加：
  ```text
  httpx>=0.27.0
  ```
- 导入检查：
  ```bash
  python -c "from app.api.routes_repositories import router; print(router.prefix)"
  ```
- 启动服务：
  ```bash
  uvicorn app.main:app --reload
  ```
- 测试接口文档：
  ```text
  http://127.0.0.1:8000/docs
  ```
- 测试创建仓库：
  ```json
  {
    "full_name": "openai/openai-python",
    "source": "manual",
    "tags": ["ai", "sdk"],
    "enabled": true
  }
  ```
- 测试列表、详情、更新：
  ```text
  GET /api/v1/repositories
  GET /api/v1/repositories/{repository_id}
  PATCH /api/v1/repositories/{repository_id}
  ```
- 错误场景：
  - `full_name` 不是 `owner/repo` 返回 400。
  - GitHub 仓库不存在返回 400。
  - 本地仓库 id 不存在返回 404。


```