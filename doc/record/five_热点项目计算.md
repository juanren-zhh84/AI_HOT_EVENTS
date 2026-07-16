```python
# 计划 6：热点项目计算代码方案

from datetime import date, datetime  # date 用来声明 report_date；datetime 用来声明日期时间字段。

from sqlalchemy import (  # SQLAlchemy 提供数据库字段类型、外键、约束和 SQL 函数。
    Boolean,  # 用来映射 MySQL 的 TINYINT(1)。
    Date,  # 用来映射 MySQL 的 DATE 字段，例如 hot_projects.report_date。
    DateTime,  # 用来映射 MySQL 的 DATETIME 字段。
    ForeignKey,  # 用来声明外键关系。
    Integer,  # 用来映射 MySQL 的 INT 字段。
    JSON,  # 用来映射 MySQL 的 JSON 字段。
    Numeric,  # 用来映射 MySQL 的 DECIMAL 字段，例如 hot_score、growth_rate_24h。
    String,  # 用来映射 MySQL 的 VARCHAR/CHAR 字段。
    Text,  # 用来映射 MySQL 的 TEXT 字段。
    UniqueConstraint,  # 用来声明联合唯一约束。
    func,  # 用来调用数据库函数。
)
```

然后在 `Repository` 类里，`snapshots` 关系下面补这个：

```python
    hot_projects: Mapped[list["HotProject"]] = relationship(  # 一个仓库可以出现在多天热点榜里，所以是一对多关系。
        back_populates="repository",  # 和 HotProject.repository 配对，方便双向访问。
        cascade="all, delete-orphan",  # 删除仓库时，ORM 层同步删除关联热点记录。
    )
```

再把下面这个类加到 `StarSnapshot` 类后面、`Job` 类前面：

```python
class HotProject(Base):  # HotProject 类对应 hot_projects 表。
    """
    hot_projects 表的 ORM 模型。

    这张表保存每天计算出来的热点项目榜单。
    它不是直接从 GitHub 来的原始数据，而是根据 star_snapshots 计算出来的结果。
    """

    __tablename__ = "hot_projects"  # 告诉 SQLAlchemy：这个类对应数据库里的 hot_projects 表。

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)  # 主键，使用 UUID 字符串。

    repository_id: Mapped[str] = mapped_column(  # 外键字段，表示这条热点记录属于哪个仓库。
        String(36),  # 类型和 repositories.id 保持一致。
        ForeignKey("repositories.id", ondelete="CASCADE", onupdate="CASCADE"),  # 仓库删除时，热点记录也一起删除。
        nullable=False,  # 热点项目必须关联一个仓库。
    )

    report_date: Mapped[date] = mapped_column(Date, nullable=False)  # 榜单日期，例如 2026-06-30。

    rank_no: Mapped[int] = mapped_column(Integer, nullable=False)  # 排名，从 1 开始。

    hot_score: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False, default=0)  # 热度分，用来排序。

    stars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 计算时的总 star 数。

    stars_delta_24h: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 近 24 小时新增 star 数。

    stars_delta_7d: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 近 7 天新增 star 数。

    growth_rate_24h: Mapped[float] = mapped_column(Numeric(12, 6), nullable=False, default=0)  # 24 小时增长率。

    reason: Mapped[str | None] = mapped_column(Text)  # 入选原因，方便邮件日报展示。

    created_at: Mapped[datetime] = mapped_column(  # 本系统创建这条热点记录的时间。
        DateTime,  # 使用 DATETIME 类型。
        nullable=False,  # 创建时间必须存在。
        server_default=func.now(),  # 插入时由数据库自动填当前时间。
    )

    updated_at: Mapped[datetime] = mapped_column(  # 本系统最后更新这条热点记录的时间。
        DateTime,  # 使用 DATETIME 类型。
        nullable=False,  # 更新时间必须存在。
        server_default=func.now(),  # 插入时由数据库自动填当前时间。
        onupdate=func.now(),  # ORM 更新记录时自动刷新更新时间。
    )

    repository: Mapped[Repository] = relationship(back_populates="hot_projects")  # 反向关联到 Repository。

    __table_args__ = (  # 表级配置，用来声明联合唯一约束。
        UniqueConstraint("report_date", "repository_id", name="uq_hot_projects_report_repo"),  # 同一天同一仓库只能有一条热点记录。
        UniqueConstraint("report_date", "rank_no", name="uq_hot_projects_report_rank"),  # 同一天同一个排名只能有一条记录。
    )
```

### 2. 新增 `app/schemas/hot_project.py`

```python
from datetime import date, datetime  # date 用来表示榜单日期；datetime 用来表示创建/更新时间。

from pydantic import BaseModel, Field  # BaseModel 定义请求体/响应体；Field 写默认值和文档说明。


class HotProjectCalculateRequest(BaseModel):  # 手动触发热点计算的请求体。
    """手动触发热点项目计算的请求体。"""

    report_date: date | None = Field(  # 允许用户指定榜单日期。
        default=None,  # 不传时使用今天。
        description="榜单日期；不传则使用当前日期。",  # 给 Swagger/Apifox 看的说明。
    )
    top_n: int = Field(  # 控制生成前多少名热点项目。
        default=20,  # 默认生成前 20 个。
        ge=1,  # 最少生成 1 个。
        le=100,  # 最多生成 100 个，避免一次计算太多。
        description="生成热点项目数量，范围 1-100。",  # 接口文档说明。
    )
    include_disabled: bool = Field(  # 是否包含暂停监控的仓库。
        default=False,  # 默认不包含暂停监控的仓库。
        description="是否包含 enabled=False 的仓库。",  # 接口文档说明。
    )


class HotProjectResponse(BaseModel):  # 单条热点项目响应体。
    """热点项目响应体。"""

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


class HotProjectRunResponse(BaseModel):  # 一次热点计算任务的整体响应体。
    """热点计算任务响应体。"""

    job_id: str  # jobs 表任务 id。
    status: str  # 任务状态。
    report_date: date  # 本次计算的榜单日期。
    total_candidates: int  # 参与计算的候选仓库数量。
    generated: int  # 最终写入 hot_projects 的数量。
    hot_projects: list[HotProjectResponse]  # 本次生成的热点项目列表。
```

### 3. 新增 `app/services/hot_project_service.py`

```python
from datetime import UTC, date, datetime, time, timedelta  # UTC 统一时间；date 是榜单日期；timedelta 用来计算 24h/7d 窗口。

from sqlalchemy import delete, select  # select 查询数据；delete 删除旧榜单，避免重复排名冲突。
from sqlalchemy.orm import Session  # Session 是数据库会话类型。

from app.db.models import HotProject, Job, Repository, StarSnapshot  # 导入热点、任务、仓库、快照 ORM 模型。


class HotProjectService:  # 热点项目业务服务。
    """根据 star_snapshots 计算热点项目，并写入 hot_projects 表。"""

    def __init__(self, db: Session) -> None:  # 初始化时传入数据库会话。
        self.db = db  # 保存数据库会话，后续查询和写入都用它。

    def calculate_hot_projects(  # 手动计算某一天热点项目。
        self,  # 当前服务对象。
        report_date: date | None = None,  # 榜单日期；None 表示今天。
        top_n: int = 20,  # 生成前多少名。
        include_disabled: bool = False,  # 是否包含暂停监控的仓库。
    ) -> dict:  # 返回 dict，FastAPI 会按 response_model 转成 JSON。
        current_report_date = report_date or datetime.now(UTC).date()  # 不传日期时使用当前 UTC 日期。
        calculated_at = datetime.now(UTC)  # 记录本次计算时间。

        job = Job(  # 创建任务记录，用来保存本次热点计算过程。
            job_type="hot_project_calculate",  # 任务类型，和 schedules 表里的名字保持接近。
            status="running",  # 刚开始计算，所以状态是 running。
            payload={  # 保存本次任务参数，方便排查。
                "report_date": current_report_date.isoformat(),  # 日期不能直接放 JSON，转成字符串。
                "top_n": top_n,  # 保存榜单数量。
                "include_disabled": include_disabled,  # 保存是否包含暂停仓库。
            },
            progress={"total_candidates": 0, "generated": 0},  # 初始化任务进度。
            started_at=calculated_at,  # 保存任务开始时间。
        )
        self.db.add(job)  # 把任务加入数据库会话。
        self.db.commit()  # 先提交 job，避免后面失败时没有任务记录。
        self.db.refresh(job)  # 刷新 job，拿到数据库生成的 id。

        repositories = self._load_repositories(include_disabled)  # 查询参与计算的仓库。
        candidates = []  # 保存计算出来的候选项目。

        for repository in repositories:  # 遍历每一个仓库。
            latest_snapshot = self._get_latest_snapshot(repository.id, calculated_at)  # 查询最新快照。
            if latest_snapshot is None:  # 如果没有任何快照。
                continue  # 没有快照就无法计算热度，跳过这个仓库。

            snapshot_24h = self._get_snapshot_before(repository.id, latest_snapshot.snapshot_at - timedelta(hours=24))  # 查询 24 小时前最近快照。
            snapshot_7d = self._get_snapshot_before(repository.id, latest_snapshot.snapshot_at - timedelta(days=7))  # 查询 7 天前最近快照。

            stars_delta_24h = self._calculate_delta(latest_snapshot, snapshot_24h)  # 计算 24 小时增长。
            stars_delta_7d = self._calculate_delta(latest_snapshot, snapshot_7d)  # 计算 7 天增长。
            growth_rate_24h = self._calculate_growth_rate(latest_snapshot, snapshot_24h)  # 计算 24 小时增长率。
            hot_score = self._calculate_hot_score(latest_snapshot.stars, stars_delta_24h, stars_delta_7d, growth_rate_24h)  # 计算热度分。

            candidates.append(  # 把候选项目加入列表，后面统一排序。
                {
                    "repository": repository,  # 保存仓库对象，方便写入 repository_id 和返回 full_name。
                    "latest_snapshot": latest_snapshot,  # 保存最新快照，方便读取当前 stars。
                    "stars_delta_24h": stars_delta_24h,  # 保存 24 小时增长。
                    "stars_delta_7d": stars_delta_7d,  # 保存 7 天增长。
                    "growth_rate_24h": growth_rate_24h,  # 保存 24 小时增长率。
                    "hot_score": hot_score,  # 保存热度分。
                }
            )

        candidates.sort(key=lambda item: item["hot_score"], reverse=True)  # 按热度分从高到低排序。
        top_candidates = candidates[:top_n]  # 只取前 top_n 个。

        self._delete_old_report(current_report_date)  # 删除同一天旧榜单，避免唯一约束冲突。

        hot_projects = []  # 保存本次写入的热点项目 ORM 对象。
        for index, candidate in enumerate(top_candidates, start=1):  # 从 1 开始生成排名。
            repository = candidate["repository"]  # 取出仓库对象。
            latest_snapshot = candidate["latest_snapshot"]  # 取出最新快照。

            hot_project = HotProject(  # 创建 hot_projects 表记录。
                repository_id=repository.id,  # 关联仓库 id。
                report_date=current_report_date,  # 保存榜单日期。
                rank_no=index,  # 保存排名。
                hot_score=round(candidate["hot_score"], 4),  # 保存热度分，保留 4 位小数。
                stars=latest_snapshot.stars,  # 保存当前总 star。
                stars_delta_24h=candidate["stars_delta_24h"],  # 保存 24 小时增长。
                stars_delta_7d=candidate["stars_delta_7d"],  # 保存 7 天增长。
                growth_rate_24h=round(candidate["growth_rate_24h"], 6),  # 保存增长率，保留 6 位小数。
                reason=self._build_reason(candidate),  # 生成人能看懂的入选原因。
            )
            self.db.add(hot_project)  # 加入数据库会话。
            hot_projects.append(hot_project)  # 保存对象，后面返回给接口。

        job.status = "succeeded"  # 能走到这里说明计算成功。
        job.progress = {"total_candidates": len(candidates), "generated": len(hot_projects)}  # 更新任务进度。
        job.finished_at = datetime.now(UTC)  # 记录结束时间。
        self.db.commit()  # 提交热点榜单和任务状态。

        for hot_project in hot_projects:  # 遍历本次写入的热点项目。
            self.db.refresh(hot_project)  # 刷新对象，拿到 created_at、updated_at 等数据库生成字段。

        return {  # 返回接口需要的数据。
            "job_id": job.id,  # 返回任务 id。
            "status": job.status,  # 返回任务状态。
            "report_date": current_report_date,  # 返回榜单日期。
            "total_candidates": len(candidates),  # 返回候选数。
            "generated": len(hot_projects),  # 返回生成数量。
            "hot_projects": [self._to_response_dict(item) for item in hot_projects],  # 转成接口响应结构。
        }

    def list_hot_projects(self, report_date: date | None = None, limit: int = 20) -> list[dict]:  # 查询某天热点榜单。
        current_report_date = report_date or datetime.now(UTC).date()  # 不传日期时查询今天。
        statement = (  # 构造查询语句。
            select(HotProject)  # 查询 hot_projects 表。
            .where(HotProject.report_date == current_report_date)  # 只查指定日期。
            .order_by(HotProject.rank_no.asc())  # 按排名升序。
            .limit(limit)  # 限制返回数量。
        )
        hot_projects = list(self.db.scalars(statement).all())  # 执行查询并转成 list。
        return [self._to_response_dict(item) for item in hot_projects]  # 转成响应字典列表。

    def _load_repositories(self, include_disabled: bool) -> list[Repository]:  # 查询参与热点计算的仓库。
        statement = select(Repository)  # 查询 repositories 表。
        if not include_disabled:  # 默认不包含暂停监控的仓库。
            statement = statement.where(Repository.enabled.is_(True))  # 只取 enabled=True。
        statement = statement.where(Repository.archived.is_(False))  # 归档仓库通常不适合作为热点推荐。
        statement = statement.where(Repository.disabled.is_(False))  # GitHub 禁用仓库不参与热点计算。
        statement = statement.order_by(Repository.stars.desc())  # 先按 stars 排序，方便稳定处理。
        return list(self.db.scalars(statement).all())  # 返回仓库列表。

    def _get_latest_snapshot(self, repository_id: str, before_time: datetime) -> StarSnapshot | None:  # 查询某仓库最新快照。
        statement = (  # 构造查询语句。
            select(StarSnapshot)  # 查询 star_snapshots 表。
            .where(StarSnapshot.repository_id == repository_id)  # 只查当前仓库。
            .where(StarSnapshot.snapshot_at <= before_time)  # 只取计算时间之前的快照。
            .order_by(StarSnapshot.snapshot_at.desc())  # 最新的排最前。
            .limit(1)  # 只要一条。
        )
        return self.db.scalar(statement)  # 查到返回 StarSnapshot，查不到返回 None。

    def _get_snapshot_before(self, repository_id: str, target_time: datetime) -> StarSnapshot | None:  # 查询目标时间之前最近快照。
        statement = (  # 构造查询语句。
            select(StarSnapshot)  # 查询 star_snapshots 表。
            .where(StarSnapshot.repository_id == repository_id)  # 只查当前仓库。
            .where(StarSnapshot.snapshot_at <= target_time)  # 找目标时间点之前的快照。
            .order_by(StarSnapshot.snapshot_at.desc())  # 离目标时间最近的排最前。
            .limit(1)  # 只取一条。
        )
        return self.db.scalar(statement)  # 查到返回 StarSnapshot，查不到返回 None。

    def _calculate_delta(self, latest_snapshot: StarSnapshot, old_snapshot: StarSnapshot | None) -> int:  # 计算 star 增长。
        if old_snapshot is None:  # 如果没有历史快照。
            return 0  # 无法计算增长，先按 0 处理。
        return max(latest_snapshot.stars - old_snapshot.stars, 0)  # 增长不允许为负，避免 GitHub 异常或数据回退影响排序。

    def _calculate_growth_rate(self, latest_snapshot: StarSnapshot, old_snapshot: StarSnapshot | None) -> float:  # 计算 24 小时增长率。
        if old_snapshot is None:  # 没有历史快照。
            return 0.0  # 无法计算增长率，返回 0。
        if old_snapshot.stars <= 0:  # 避免除以 0。
            return 0.0  # 历史 stars 为 0 时先返回 0。
        return max((latest_snapshot.stars - old_snapshot.stars) / old_snapshot.stars, 0.0)  # 只保留正增长率。

    def _calculate_hot_score(self, stars: int, delta_24h: int, delta_7d: int, growth_rate_24h: float) -> float:  # 计算热度分。
        star_base_score = min(stars, 100000) * 0.001  # 总 stars 给少量基础分，避免老项目完全没权重。
        daily_growth_score = delta_24h * 5  # 24 小时增长权重最高，因为它最能代表“今天热”。
        weekly_growth_score = delta_7d * 1  # 7 天增长权重较低，用来补充趋势。
        growth_rate_score = growth_rate_24h * 100  # 增长率给额外加分，照顾小而快的项目。
        return star_base_score + daily_growth_score + weekly_growth_score + growth_rate_score  # 返回最终热度分。

    def _build_reason(self, candidate: dict) -> str:  # 生成入选原因。
        delta_24h = candidate["stars_delta_24h"]  # 取出 24 小时增长。
        delta_7d = candidate["stars_delta_7d"]  # 取出 7 天增长。
        hot_score = candidate["hot_score"]  # 取出热度分。
        return f"近24小时新增 {delta_24h} stars，近7天新增 {delta_7d} stars，热度分 {hot_score:.2f}。"  # 返回可读文案。

    def _delete_old_report(self, report_date: date) -> None:  # 删除同一天旧榜单。
        statement = delete(HotProject).where(HotProject.report_date == report_date)  # 构造删除语句。
        self.db.execute(statement)  # 执行删除；等外层 commit 一起提交。

    def _to_response_dict(self, hot_project: HotProject) -> dict:  # 把 ORM 对象转成接口响应字典。
        repository = hot_project.repository  # 通过 ORM 关系拿到仓库对象。
        return {  # 返回响应模型需要的字段。
            "id": hot_project.id,  # 热点记录 id。
            "repository_id": hot_project.repository_id,  # 仓库 id。
            "full_name": repository.full_name,  # 仓库完整名。
            "html_url": repository.html_url,  # GitHub 地址。
            "description": repository.description,  # 仓库描述。
            "primary_language": repository.primary_language,  # 主语言。
            "report_date": hot_project.report_date,  # 榜单日期。
            "rank_no": hot_project.rank_no,  # 排名。
            "hot_score": float(hot_project.hot_score),  # Decimal 转 float，方便 JSON 返回。
            "stars": hot_project.stars,  # 当前总 stars。
            "stars_delta_24h": hot_project.stars_delta_24h,  # 24 小时增长。
            "stars_delta_7d": hot_project.stars_delta_7d,  # 7 天增长。
            "growth_rate_24h": float(hot_project.growth_rate_24h),  # Decimal 转 float。
            "reason": hot_project.reason,  # 入选原因。
            "created_at": hot_project.created_at,  # 创建时间。
            "updated_at": hot_project.updated_at,  # 更新时间。
        }
```

### 4. 新增 `app/api/routes_hot_projects.py`

```python
from datetime import date  # date 用来声明查询参数 report_date。

from fastapi import APIRouter, Depends, Query, status  # APIRouter 定义路由；Depends 注入依赖；Query 定义查询参数；status 提供状态码。
from sqlalchemy.orm import Session  # Session 用来标注数据库会话类型。

from app.db.session import get_db  # get_db 为每次请求提供数据库会话。
from app.schemas.hot_project import HotProjectCalculateRequest, HotProjectResponse, HotProjectRunResponse  # 导入请求体和响应体。
from app.services.hot_project_service import HotProjectService  # 导入热点项目业务服务。


router = APIRouter(prefix="/hot-projects", tags=["hot_projects"])  # 当前文件的接口统一以 /hot-projects 开头。


@router.post("/runs", response_model=HotProjectRunResponse, status_code=status.HTTP_201_CREATED)  # POST /hot-projects/runs 手动计算热点榜。
def calculate_hot_projects(payload: HotProjectCalculateRequest, db: Session = Depends(get_db)) -> HotProjectRunResponse:  # 接收请求体和数据库会话。
    service = HotProjectService(db)  # 创建业务服务对象。
    return service.calculate_hot_projects(payload.report_date, payload.top_n, payload.include_disabled)  # 执行热点计算。


@router.get("", response_model=list[HotProjectResponse])  # GET /hot-projects 查询热点榜单。
def list_hot_projects(  # 定义热点榜单查询接口。
    report_date: date | None = Query(default=None, description="榜单日期；不传则查询今天。"),  # 可选查询日期。
    limit: int = Query(default=20, ge=1, le=100, description="返回数量，范围 1-100。"),  # 限制返回数量。
    db: Session = Depends(get_db),  # 注入数据库会话。
) -> list[HotProjectResponse]:  # 返回热点项目列表。
    service = HotProjectService(db)  # 创建业务服务对象。
    return service.list_hot_projects(report_date, limit)  # 查询并返回热点榜单。
```

### 5. 修改 `app/main.py`

```python
from fastapi import FastAPI  # FastAPI 是应用入口类。

from app.api.routes_health import router as health_router  # 健康检查路由。
from app.api.routes_hot_projects import router as hot_projects_router  # 热点项目路由。
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
app.include_router(hot_projects_router, prefix="/api/v1")  # 注册热点项目接口。


@app.get("/", include_in_schema=False)  # 根路径接口，不放进接口文档。
def root() -> dict[str, str]:  # 返回服务基础信息。
    return {  # 返回一个简单字典。
        "service": settings.app_name,  # 服务名称。
        "docs": "/docs",  # 文档地址。
        "health": "/api/v1/health",  # 健康检查地址。
    }
```

## API Usage
手动计算热点榜：

```text
POST /api/v1/hot-projects/runs
```

请求体：

```json
{
  "top_n": 20,
  "include_disabled": false
}
```

查询今天热点榜：

```text
GET /api/v1/hot-projects?limit=20
```

查询指定日期热点榜：

```text
GET /api/v1/hot-projects?report_date=2026-06-30&limit=20
```

## Test Plan
1. 先确认第 5 步已有快照数据：

```sql
SELECT repository_id, stars, snapshot_at
FROM star_snapshots
ORDER BY snapshot_at DESC
LIMIT 10;
```

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

4. 调用：

```text
POST /api/v1/hot-projects/runs
```

5. 验证数据库：

```sql
SELECT report_date, rank_no, repository_id, hot_score, stars, stars_delta_24h, stars_delta_7d, growth_rate_24h, reason
FROM hot_projects
ORDER BY report_date DESC, rank_no ASC;
```

6. 查询接口验证：

```text
GET /api/v1/hot-projects?limit=20
```

## Assumptions
- 这一步只做手动热点计算，不接定时任务。
- 如果仓库只有 1 条快照，`stars_delta_24h` 和 `stars_delta_7d` 会是 `0`，但仍然可以生成热点记录。
- 热度分公式先用可解释版本：总 stars 少量基础分 + 24h 增长高权重 + 7d 增长低权重 + 24h 增长率加分。
- 后续第 7 步邮件日报会直接读取 `hot_projects` 表。

```
