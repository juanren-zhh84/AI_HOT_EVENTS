```python
# 计划 5：星标快照采集代码方案

## Code

### 1. 新增 `app/schemas/star_snapshot.py`

from datetime import datetime  # 导入 datetime，用来声明响应里的快照时间、创建时间字段。

from pydantic import BaseModel, Field  # BaseModel 用来定义请求体/响应体；Field 用来写默认值、示例和说明。


class StarSnapshotRunRequest(BaseModel):  # 定义“手动触发星标快照采集”的请求体。
    """手动触发星标快照采集的请求体。"""

    repository_ids: list[str] | None = Field(  # 指定要采集的仓库 id 列表；None 表示不指定。
        default=None,  # 默认 None，表示采集所有启用监控的仓库。
        description="指定仓库 ID 列表；不传则采集所有 enabled=True 的仓库。",  # 给 Swagger/Apifox看的字段说明。
    )
    include_disabled: bool = Field(  # 是否包含已经暂停监控的仓库。
        default=False,  # 默认不采集 disabled/enabled=False 的仓库，避免误采集已暂停项目。
        description="是否采集已暂停监控的仓库；默认 False。",  # 给接口文档看的说明。
    )


class StarSnapshotError(BaseModel):  # 定义单个仓库采集失败时的错误结构。
    """单个仓库采集失败时的错误信息。"""

    repository_id: str | None = None  # 仓库 id；如果 id 本身不存在，也会把请求里的 id 放这里。
    full_name: str | None = None  # GitHub 仓库全名；如果仓库没查到，可能为空。
    error_message: str  # 失败原因，例如 GitHub 404、限流、网络错误等。


class StarSnapshotResponse(BaseModel):  # 定义单条星标快照的响应体。
    """星标快照响应体。"""

    id: str  # 快照记录在本系统数据库里的 UUID。
    repository_id: str  # 这条快照属于哪个仓库。
    stars: int  # 快照时刻的 star 数。
    forks: int  # 快照时刻的 fork 数。
    watchers: int  # 快照时刻的 watcher 数。
    open_issues: int  # 快照时刻的 open issue 数。
    source: str  # 快照来源，例如 github_rest。
    snapshot_at: datetime  # 采集快照的时间点。
    created_at: datetime  # 这条快照写入数据库的时间。

    model_config = {"from_attributes": True}  # 允许 FastAPI 直接把 SQLAlchemy ORM 对象转换成响应 JSON。


class StarSnapshotRunResponse(BaseModel):  # 定义一次采集任务的整体响应体。
    """手动采集任务的整体响应体。"""

    job_id: str  # jobs 表里的任务 id，方便后续排查本次执行。
    status: str  # 任务状态：succeeded 或 failed。
    total: int  # 本次计划采集的仓库数量。
    succeeded: int  # 本次成功采集的仓库数量。
    failed: int  # 本次失败的仓库数量。
    snapshots: list[StarSnapshotResponse]  # 本次成功写入的快照列表。
    errors: list[StarSnapshotError]  # 本次失败的仓库错误列表。
```

### 2. 新增 `app/services/star_snapshot_service.py`

```python
from datetime import UTC, datetime  # UTC 保证采集时间统一；datetime 用来记录开始/结束/快照时间。

import httpx  # 捕获 GitHub 请求失败，例如 404、403、网络超时。
from sqlalchemy import select  # SQLAlchemy 2.x 推荐用 select 构造查询。
from sqlalchemy.exc import IntegrityError  # 捕获唯一约束冲突等数据库写入错误。
from sqlalchemy.orm import Session  # Session 是数据库会话类型，用来查询和提交事务。

from app.db.models import Job, Repository, StarSnapshot  # 导入 jobs、repositories、star_snapshots 三张表的 ORM 模型。
from app.services.github_client import GitHubClient  # GitHubClient 负责真正请求 GitHub API。
from app.services.repository_service import parse_github_datetime  # 复用已有 GitHub 时间字符串转换函数。


class StarSnapshotService:  # 星标快照业务服务，专门处理第 5 步逻辑。
    """负责手动采集 GitHub 仓库指标，并写入 star_snapshots。"""

    def __init__(self, db: Session) -> None:  # 初始化服务时传入数据库会话。
        self.db = db  # 保存数据库会话，后续查询、写入、提交都使用它。
        self.github_client = GitHubClient()  # 创建 GitHub 客户端，用来获取最新仓库指标。

    def list_snapshots(self, repository_id: str, limit: int = 20) -> list[StarSnapshot]:  # 查询某个仓库的快照列表。
        statement = (  # 构造 SQLAlchemy 查询语句。
            select(StarSnapshot)  # 查询 star_snapshots 表对应的 ORM 对象。
            .where(StarSnapshot.repository_id == repository_id)  # 只查指定仓库的快照。
            .order_by(StarSnapshot.snapshot_at.desc())  # 最新快照排在最前面，方便查看最近采集结果。
            .limit(limit)  # 限制返回数量，避免一次返回太多数据。
        )
        return list(self.db.scalars(statement).all())  # 执行查询，并把结果转成普通 list 返回。

    def run_snapshot(  # 手动执行一次星标快照采集。
        self,  # 当前服务对象。
        repository_ids: list[str] | None = None,  # 指定仓库 id；None 表示采集所有启用仓库。
        include_disabled: bool = False,  # 是否包含已暂停监控的仓库。
    ) -> dict:  # 返回 dict，FastAPI 会按 response_model 转成规范 JSON。
        normalized_ids = self._normalize_repository_ids(repository_ids)  # 清理 id 列表，去空格并去重。
        started_at = datetime.now(UTC)  # 记录任务开始时间，统一使用 UTC。

        job = Job(  # 创建一条任务记录，用来记录这次采集过程。
            job_type="star_snapshot",  # 数据库字段叫 type，ORM 属性叫 job_type，表示任务类型。
            status="running",  # 刚开始执行，所以状态是 running。
            payload={  # payload 保存本次任务参数，方便以后排查。
                "repository_ids": normalized_ids,  # 保存本次指定的仓库 id。
                "include_disabled": include_disabled,  # 保存是否包含暂停监控仓库。
            },
            progress={"total": 0, "succeeded": 0, "failed": 0},  # 初始化任务进度。
            started_at=started_at,  # 保存任务开始时间。
        )
        self.db.add(job)  # 把任务对象加入数据库会话。
        self.db.commit()  # 先提交任务记录，这样即使后面采集失败，也能留下 job。
        self.db.refresh(job)  # 刷新任务对象，拿到数据库生成的 id。

        repositories = self._load_target_repositories(normalized_ids, include_disabled)  # 查询本次真正需要采集的仓库。
        errors = self._build_skipped_errors(normalized_ids, repositories)  # 生成“仓库不存在或被跳过”的错误。
        snapshots: list[StarSnapshot] = []  # 保存本次成功写入的快照对象。
        succeeded_count = 0  # 成功计数从 0 开始。
        failed_count = len(errors)  # 失败计数先包含不存在或被跳过的仓库。

        total_count = len(normalized_ids) if normalized_ids is not None else len(repositories)  # 指定 id 时按请求数量统计，否则按查询到的仓库数量统计。

        for repository in repositories:  # 逐个仓库请求 GitHub 并写入快照。
            try:  # 单个仓库失败不应该影响其他仓库继续采集。
                github_data = self.github_client.get_repository(repository.owner, repository.name)  # 获取 GitHub 最新仓库数据。
                snapshot_at = datetime.now(UTC)  # 记录这条快照的采集时间。

                self._sync_repository_metrics(repository, github_data, snapshot_at)  # 同步 repositories 表里的当前指标。
                snapshot = self._create_snapshot(repository, snapshot_at)  # 根据当前仓库指标创建 StarSnapshot 对象。

                self.db.add(snapshot)  # 把快照加入数据库会话。
                self.db.commit()  # 提交当前仓库的快照；逐个提交可以避免一个失败影响全部。
                self.db.refresh(snapshot)  # 刷新快照对象，拿到数据库最终值。
                snapshots.append(snapshot)  # 保存成功快照，最后返回给接口调用方。
                succeeded_count += 1  # 成功数量加 1。
            except httpx.HTTPError as exc:  # 捕获 GitHub HTTP 错误或网络错误。
                self.db.rollback()  # 回滚当前仓库未提交的数据库改动，避免脏数据。
                failed_count += 1  # 失败数量加 1。
                errors.append(  # 把失败原因记录到响应里。
                    {
                        "repository_id": repository.id,  # 失败仓库 id。
                        "full_name": repository.full_name,  # 失败仓库全名。
                        "error_message": self._format_http_error(repository, exc),  # 转成人能看懂的错误说明。
                    }
                )
            except IntegrityError as exc:  # 捕获数据库唯一约束等写入错误。
                self.db.rollback()  # 数据库写入失败后必须 rollback，否则 Session 不能继续使用。
                failed_count += 1  # 失败数量加 1。
                errors.append(  # 把数据库错误写进响应。
                    {
                        "repository_id": repository.id,  # 失败仓库 id。
                        "full_name": repository.full_name,  # 失败仓库全名。
                        "error_message": f"写入 star_snapshots 失败：{exc.orig}",  # 记录底层数据库错误。
                    }
                )

        job.status = "succeeded" if failed_count == 0 else "failed"  # 只要有失败，就把任务标记为 failed，方便排查。
        job.progress = {"total": total_count, "succeeded": succeeded_count, "failed": failed_count}  # 更新最终进度。
        job.error_message = self._join_error_messages(errors)  # 把错误列表压缩成文本，保存到 jobs.error_message。
        job.finished_at = datetime.now(UTC)  # 记录任务结束时间。
        self.db.commit()  # 提交任务最终状态。
        self.db.refresh(job)  # 刷新任务对象，确保返回的是数据库最终状态。

        return {  # 返回接口响应需要的数据。
            "job_id": job.id,  # 返回任务 id。
            "status": job.status,  # 返回任务状态。
            "total": total_count,  # 返回总数。
            "succeeded": succeeded_count,  # 返回成功数。
            "failed": failed_count,  # 返回失败数。
            "snapshots": snapshots,  # 返回成功快照列表。
            "errors": errors,  # 返回失败明细。
        }

    def _normalize_repository_ids(self, repository_ids: list[str] | None) -> list[str] | None:  # 清理请求里的仓库 id。
        if repository_ids is None:  # None 表示用户没有指定仓库 id。
            return None  # 保留 None，后续用它表示“采集所有启用仓库”。

        normalized_ids: list[str] = []  # 用列表保存清理后的 id，同时保留用户传入顺序。
        for repository_id in repository_ids:  # 遍历用户传入的每个 id。
            clean_id = repository_id.strip()  # 去掉前后空格，避免复制 id 时多了空格导致查不到。
            if clean_id and clean_id not in normalized_ids:  # 空字符串不要；重复 id 只保留一次。
                normalized_ids.append(clean_id)  # 保存有效 id。
        return normalized_ids  # 返回清理后的 id 列表。

    def _load_target_repositories(  # 查询本次需要采集的仓库。
        self,  # 当前服务对象。
        repository_ids: list[str] | None,  # 指定仓库 id；None 表示查所有。
        include_disabled: bool,  # 是否包含暂停监控的仓库。
    ) -> list[Repository]:  # 返回 Repository ORM 对象列表。
        statement = select(Repository)  # 先构造查询 repositories 表的语句。

        if repository_ids is not None:  # 如果用户指定了仓库 id。
            if not repository_ids:  # 如果用户传的是空列表。
                return []  # 空列表表示没有目标仓库，直接返回空结果。
            statement = statement.where(Repository.id.in_(repository_ids))  # 只查询这些 id 对应的仓库。

        if not include_disabled:  # 默认不采集已暂停监控的仓库。
            statement = statement.where(Repository.enabled.is_(True))  # 只保留 enabled=True 的仓库。

        statement = statement.order_by(Repository.created_at.asc())  # 按创建时间排序，让采集顺序稳定。
        repositories = list(self.db.scalars(statement).all())  # 执行查询，得到仓库列表。

        if repository_ids is None:  # 如果不是指定 id 模式。
            return repositories  # 直接返回全部目标仓库。

        repository_map = {repository.id: repository for repository in repositories}  # 建立 id -> 仓库对象的映射。
        return [repository_map[repository_id] for repository_id in repository_ids if repository_id in repository_map]  # 按用户传入顺序返回。

    def _build_skipped_errors(  # 生成“没查到或被跳过”的错误列表。
        self,  # 当前服务对象。
        repository_ids: list[str] | None,  # 用户指定的仓库 id。
        repositories: list[Repository],  # 实际查到并准备采集的仓库。
    ) -> list[dict]:  # 返回错误 dict 列表。
        if repository_ids is None:  # 如果用户没有指定 id。
            return []  # 自动采集全部启用仓库时，没有“指定 id 不存在”的问题。

        selected_ids = {repository.id for repository in repositories}  # 实际会被采集的仓库 id 集合。
        errors: list[dict] = []  # 准备错误列表。
        for repository_id in repository_ids:  # 遍历用户请求里的每个仓库 id。
            if repository_id not in selected_ids:  # 如果这个 id 没有进入采集列表。
                errors.append(  # 记录为失败项。
                    {
                        "repository_id": repository_id,  # 返回用户传入的 id。
                        "full_name": None,  # 没查到仓库对象，所以没有 full_name。
                        "error_message": "仓库不存在，或该仓库已暂停监控且 include_disabled=false。",  # 告诉用户可能原因。
                    }
                )
        return errors  # 返回跳过错误列表。

    def _sync_repository_metrics(  # 把 GitHub 最新指标同步回 repositories 表。
        self,  # 当前服务对象。
        repository: Repository,  # 当前要更新的仓库对象。
        github_data: dict,  # GitHub API 返回的仓库详情。
        collected_at: datetime,  # 本次采集时间。
    ) -> None:  # 只修改 ORM 对象，不直接返回值。
        repository.stars = github_data.get("stargazers_count") or 0  # 更新当前 star 数。
        repository.forks = github_data.get("forks_count") or 0  # 更新当前 fork 数。
        repository.watchers = github_data.get("watchers_count") or 0  # 更新当前 watcher 数。
        repository.open_issues = github_data.get("open_issues_count") or 0  # 更新当前 open issue 数。
        repository.archived = github_data.get("archived") or False  # 更新 GitHub 是否归档。
        repository.disabled = github_data.get("disabled") or False  # 更新 GitHub 是否禁用。
        repository.primary_language = github_data.get("language")  # 更新主语言，方便后续热点筛选。
        repository.topics = github_data.get("topics") or []  # 更新 GitHub topics，None 时保存空列表。
        repository.github_updated_at = parse_github_datetime(github_data.get("updated_at"))  # 更新 GitHub 更新时间。
        repository.last_pushed_at = parse_github_datetime(github_data.get("pushed_at"))  # 更新最近 push 时间。
        repository.last_collected_at = collected_at  # 更新本系统最近采集时间。

    def _create_snapshot(self, repository: Repository, snapshot_at: datetime) -> StarSnapshot:  # 创建快照 ORM 对象。
        return StarSnapshot(  # 返回一条还没提交数据库的快照对象。
            repository_id=repository.id,  # 关联当前仓库 id。
            stars=repository.stars,  # 保存本次采集到的 star 数。
            forks=repository.forks,  # 保存本次采集到的 fork 数。
            watchers=repository.watchers,  # 保存本次采集到的 watcher 数。
            open_issues=repository.open_issues,  # 保存本次采集到的 open issue 数。
            source="github_rest",  # 标记数据来源为 GitHub REST API。
            snapshot_at=snapshot_at,  # 保存快照采集时间。
        )

    def _format_http_error(self, repository: Repository, exc: httpx.HTTPError) -> str:  # 把 httpx 异常转成易懂文案。
        if isinstance(exc, httpx.HTTPStatusError):  # HTTPStatusError 表示 GitHub 返回了 4xx/5xx。
            status_code = exc.response.status_code  # 取出 HTTP 状态码。
            if status_code == 404:  # 404 表示 GitHub 上找不到这个仓库。
                return f"GitHub 仓库不存在：{repository.full_name}"  # 返回更明确的提示。
            if status_code == 403:  # 403 常见原因是 token 权限不足或 API 限流。
                return f"GitHub API 拒绝访问或限流：{repository.full_name}"  # 返回限流/权限提示。
            return f"GitHub API 请求失败，状态码 {status_code}：{repository.full_name}"  # 其他状态码统一说明。
        return f"请求 GitHub 失败：{repository.full_name}，原因：{exc}"  # 网络错误、超时等走这里。

    def _join_error_messages(self, errors: list[dict]) -> str | None:  # 把错误列表合并成 jobs.error_message。
        if not errors:  # 如果没有错误。
            return None  # 数据库错误字段保存为空。
        return "\n".join(error["error_message"] for error in errors)  # 多个错误用换行拼起来，方便查看。
```

### 3. 新增 `app/api/routes_star_snapshots.py`

```python
from fastapi import APIRouter, Depends, Query, status  # APIRouter 定义路由；Depends 注入依赖；Query 定义查询参数；status 提供状态码常量。
from sqlalchemy.orm import Session  # Session 用来标注数据库会话类型。

from app.db.session import get_db  # get_db 会为每次请求提供一个数据库会话，并在请求结束后关闭。
from app.schemas.star_snapshot import StarSnapshotResponse, StarSnapshotRunRequest, StarSnapshotRunResponse  # 导入请求体和响应体模型。
from app.services.star_snapshot_service import StarSnapshotService  # 导入星标快照业务服务。


router = APIRouter(prefix="/star-snapshots", tags=["star_snapshots"])  # 当前文件的接口统一以 /star-snapshots 开头。


@router.post("/runs", response_model=StarSnapshotRunResponse, status_code=status.HTTP_201_CREATED)  # POST /star-snapshots/runs 手动触发采集。
def run_star_snapshot(payload: StarSnapshotRunRequest, db: Session = Depends(get_db)) -> StarSnapshotRunResponse:  # 接收请求体和数据库会话。
    service = StarSnapshotService(db)  # 创建业务服务对象。
    return service.run_snapshot(payload.repository_ids, payload.include_disabled)  # 执行采集，并返回任务结果。


@router.get("", response_model=list[StarSnapshotResponse])  # GET /star-snapshots 查询某个仓库的快照。
def list_star_snapshots(  # 定义快照列表接口。
    repository_id: str = Query(..., description="仓库 ID。"),  # 必填查询参数，告诉接口查哪个仓库。
    limit: int = Query(default=20, ge=1, le=100, description="返回数量，范围 1-100。"),  # 限制返回数量，避免响应太大。
    db: Session = Depends(get_db),  # 注入数据库会话。
) -> list[StarSnapshotResponse]:  # 返回快照响应体列表。
    service = StarSnapshotService(db)  # 创建业务服务对象。
    return service.list_snapshots(repository_id, limit)  # 查询并返回指定仓库快照。
```

### 4. 修改 `app/main.py`

```python
from fastapi import FastAPI  # FastAPI 是应用入口类。

from app.api.routes_health import router as health_router  # 健康检查路由。
from app.api.routes_repositories import router as repositories_router  # 仓库管理路由。
from app.api.routes_star_snapshots import router as star_snapshots_router  # 星标快照路由。
from app.core.config import settings  # 应用配置。


app = FastAPI(  # 创建 FastAPI 应用。
    title=settings.app_name,  # 应用名称。
    version=settings.app_version,  # 应用版本。
    docs_url="/docs",  # Swagger 文档地址。
    openapi_url="/openapi.json",  # OpenAPI JSON 地址。
)

app.include_router(health_router, prefix="/api/v1")  # 注册健康检查接口。
app.include_router(repositories_router, prefix="/api/v1")  # 注册仓库接口。
app.include_router(star_snapshots_router, prefix="/api/v1")  # 注册星标快照接口。


@app.get("/", include_in_schema=False)  # 根路径接口，不放进接口文档。
def root() -> dict[str, str]:  # 返回服务基础信息。
    return {  # 返回一个简单字典。
        "service": settings.app_name,  # 服务名称。
        "docs": "/docs",  # 文档地址。
        "health": "/api/v1/health",  # 健康检查地址。
    }
```

## API Usage

新增接口：

```text
POST /api/v1/star-snapshots/runs
```

采集所有启用仓库：

```json
{}
```

采集指定仓库：

```json
{
  "repository_ids": ["这里填 repositories 表里的 id"],
  "include_disabled": false
}
```

查询某个仓库快照：

```text
GET /api/v1/star-snapshots?repository_id=这里填仓库id&limit=20
```

## Test Plan

1. 启动 MySQL，确认 `MySQL84` 是 `Running`。
2. 启动服务：

```powershell
cd D:\pythonworking\AI_Hot_Events
conda activate aihotevent
python -m uvicorn app.main:app --reload
```

3. 打开：

```text
http://127.0.0.1:8000/docs
```

4. 先保证 `repositories` 里至少有一个仓库。
5. 调用 `POST /api/v1/star-snapshots/runs`，请求体填 `{}`。
6. MySQL 验证：

```sql
SELECT repository_id, stars, forks, watchers, open_issues, snapshot_at
FROM star_snapshots
ORDER BY created_at DESC
LIMIT 10;

SELECT type, status, progress, error_message
FROM jobs
ORDER BY created_at DESC
LIMIT 5;
```

```