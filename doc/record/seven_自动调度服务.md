# 计划 8：自动调度服务代码方案

## Summary

第 8 步实现“自动调度服务”：让系统启动后自动按 `.env` 里的 cron 配置执行任务，不再完全依赖 Apifox 手动点接口。

本阶段要自动执行 3 个任务：

```text
1. 每小时采集 GitHub star 快照
2. 每天 08:30 计算热点项目
3. 每天 09:00 发送邮件日报
```

注意：我查了当前可安装的 APScheduler 版本，`pip` 最新稳定版本是 `3.11.3`，所以这里使用 APScheduler 3.x 的 `BackgroundScheduler` 写法，不使用 APScheduler 4.x 的新 API，避免你安装后 import 报错。

## Key Changes

需要新增/修改：

- 修改 `requirements.txt`
  - 新增 `APScheduler==3.11.3`

- 修改 `app/core/config.py`
  - 新增 `scheduler_enabled`
  - 继续复用已有的：
    - `star_snapshot_cron`
    - `hot_project_cron`
    - `digest_cron`
    - `hot_project_top_n`
    - `timezone`

- 新增 `app/services/scheduler_service.py`
  - 统一管理后台调度器
  - 注册 3 个定时任务
  - 每个任务单独创建数据库 Session
  - 每个任务自己捕获异常，避免任务失败导致 FastAPI 服务退出

- 修改 `app/main.py`
  - 使用 FastAPI `lifespan`
  - 应用启动时启动调度器
  - 应用关闭时停止调度器

## Code

### 1. 修改 `requirements.txt`

追加一行：

```txt
APScheduler==3.11.3
```

为什么固定版本？

因为调度库的 API 和版本强相关。当前稳定可安装版本是 3.11.3，本方案也按 3.x 写法来写，固定版本可以避免后续安装到不兼容版本。

### 2. 修改 `app/core/config.py`

在 `Settings` 类里增加一个配置：

```python
scheduler_enabled: bool = True  # 是否启用后台调度器；本地调试不想自动跑任务时，可以在 .env 里设为 false。
```

放在 cron 配置附近即可，例如：

```python
    discovery_cron: str = "0 */6 * * *"
    star_snapshot_cron: str = "0 * * * *"
    profile_refresh_cron: str = "0 2 * * *"
    hot_project_cron: str = "30 8 * * *"
    digest_cron: str = "0 9 * * *"
    hot_project_top_n: int = 20
    scheduler_enabled: bool = True  # 是否启用后台调度器；生产环境通常开启，本地调试可关闭。
```

`.env` 可选增加：

```env
SCHEDULER_ENABLED=true
STAR_SNAPSHOT_CRON=0 * * * *
HOT_PROJECT_CRON=30 8 * * *
DIGEST_CRON=0 9 * * *
HOT_PROJECT_TOP_N=20
```

### 3. 新增 `app/services/scheduler_service.py`

```python
import logging  # Python 标准日志库，用来记录调度器启动、停止、任务成功、任务失败。
from collections.abc import Callable  # 用来给“接收数据库 Session 的函数”做类型标注。
from zoneinfo import ZoneInfo  # Python 标准库时区工具，用来让 cron 按 Asia/Shanghai 运行。

from apscheduler.schedulers.background import BackgroundScheduler  # APScheduler 3.x 后台调度器，不阻塞 FastAPI 主线程。
from apscheduler.triggers.cron import CronTrigger  # cron 触发器，支持 0 9 * * * 这种表达式。
from sqlalchemy.orm import Session  # SQLAlchemy 数据库会话类型。

from app.core.config import settings  # 读取 .env 里的 cron、时区、开关等配置。
from app.db.session import SessionLocal  # 定时任务不是 HTTP 请求，所以要自己创建数据库 Session。
from app.services.email_digest_service import EmailDigestService  # 邮件日报服务。
from app.services.hot_project_service import HotProjectService  # 热点项目计算服务。
from app.services.star_snapshot_service import StarSnapshotService  # 星标快照采集服务。


logger = logging.getLogger(__name__)  # 获取当前模块的日志对象，日志会交给 uvicorn/Python 日志系统输出。


class SchedulerService:  # 调度器服务类，负责启动、停止、注册和执行后台任务。
    """管理后台定时任务。"""

    def __init__(self) -> None:  # 初始化调度器服务。
        self.scheduler: BackgroundScheduler | None = None  # 保存 APScheduler 实例；未启动前为 None。
        self.timezone = ZoneInfo(settings.timezone)  # 使用配置里的时区，保证 09:00 是中国时间的 09:00。

    def start(self) -> None:  # 启动调度器。
        if not settings.scheduler_enabled:  # 如果 .env 里关闭了调度器。
            logger.info("Scheduler is disabled by SCHEDULER_ENABLED=false.")  # 记录日志，方便确认为什么没启动。
            return  # 直接返回，不注册任何任务。

        if self.scheduler is not None and self.scheduler.running:  # 如果调度器已经启动。
            logger.info("Scheduler is already running.")  # 记录日志，避免重复启动。
            return  # 避免重复注册任务。

        self.scheduler = BackgroundScheduler(timezone=self.timezone)  # 创建后台调度器，后台线程执行任务。
        self._register_jobs()  # 注册星标快照、热点计算、邮件日报 3 个任务。
        self.scheduler.start()  # 启动调度器；启动后不会阻塞 FastAPI。
        logger.info("Scheduler started.")  # 记录启动成功。

    def stop(self) -> None:  # 停止调度器。
        if self.scheduler is None:  # 如果调度器从未启动。
            logger.info("Scheduler is not initialized.")  # 记录日志。
            return  # 没有东西需要停止。

        if self.scheduler.running:  # 如果调度器正在运行。
            self.scheduler.shutdown(wait=False)  # 停止调度器；wait=False 表示不等待正在执行的任务结束。
            logger.info("Scheduler stopped.")  # 记录停止成功。

        self.scheduler = None  # 清空引用，避免服务下次启动时复用已关闭的调度器。

    def _register_jobs(self) -> None:  # 注册所有后台任务。
        self._add_cron_job(  # 注册星标快照采集任务。
            job_id="star_snapshot_job",  # 任务 id，日志和调度器内部都会用到。
            cron_expression=settings.star_snapshot_cron,  # 从 .env 读取星标快照 cron。
            job_func=self._run_star_snapshot_job,  # 到点后执行这个函数。
        )
        self._add_cron_job(  # 注册热点项目计算任务。
            job_id="hot_project_job",  # 任务 id。
            cron_expression=settings.hot_project_cron,  # 从 .env 读取热点计算 cron。
            job_func=self._run_hot_project_job,  # 到点后执行这个函数。
        )
        self._add_cron_job(  # 注册邮件日报发送任务。
            job_id="email_digest_job",  # 任务 id。
            cron_expression=settings.digest_cron,  # 从 .env 读取邮件日报 cron。
            job_func=self._run_email_digest_job,  # 到点后执行这个函数。
        )

    def _add_cron_job(self, job_id: str, cron_expression: str, job_func: Callable[[], None]) -> None:  # 添加单个 cron 任务。
        if self.scheduler is None:  # 理论上 start() 里已经创建 scheduler，这里防御一下。
            raise RuntimeError("Scheduler is not initialized.")  # 如果没初始化就注册任务，说明调用顺序错了。

        trigger = CronTrigger.from_crontab(cron_expression, timezone=self.timezone)  # 把 0 9 * * * 转成 APScheduler 触发器。

        self.scheduler.add_job(  # 把任务交给 APScheduler 管理。
            func=job_func,  # 到时间后执行的函数。
            trigger=trigger,  # cron 触发规则。
            id=job_id,  # 任务唯一 id。
            name=job_id,  # 任务名称，方便日志和调试。
            replace_existing=True,  # 重复注册同名任务时覆盖旧任务，避免 reload 后重复。
            max_instances=1,  # 同一个任务最多同时跑 1 个，避免上一次没跑完下一次又开始。
            coalesce=True,  # 如果服务短暂停顿错过多次触发，只补跑一次，避免任务堆积。
            misfire_grace_time=300,  # 错过触发时间 300 秒内仍允许执行，超过就跳过。
        )

        logger.info("Registered schedule %s with cron %s.", job_id, cron_expression)  # 记录注册结果。

    def _run_star_snapshot_job(self) -> None:  # 执行星标快照采集任务。
        self._run_with_session(  # 用统一方法创建和关闭数据库 Session。
            job_name="star_snapshot_job",  # 当前任务名称。
            runner=lambda db: StarSnapshotService(db).run_snapshot(),  # 创建服务并采集所有启用仓库。
        )

    def _run_hot_project_job(self) -> None:  # 执行热点项目计算任务。
        self._run_with_session(  # 用统一方法创建和关闭数据库 Session。
            job_name="hot_project_job",  # 当前任务名称。
            runner=lambda db: HotProjectService(db).calculate_hot_projects(  # 创建服务并计算热点项目。
                report_date=None,  # 不指定日期时，服务内部默认使用今天。
                top_n=settings.hot_project_top_n,  # 使用配置里的榜单数量。
                include_disabled=False,  # 默认不计算已暂停监控的仓库。
            ),
        )

    def _run_email_digest_job(self) -> None:  # 执行邮件日报发送任务。
        self._run_with_session(  # 用统一方法创建和关闭数据库 Session。
            job_name="email_digest_job",  # 当前任务名称。
            runner=lambda db: EmailDigestService(db).run_digest(  # 创建服务并发送邮件日报。
                report_date=None,  # 不指定日期时，服务内部默认使用今天。
                top_n=settings.hot_project_top_n,  # 邮件里展示配置数量的热点项目。
                dry_run=False,  # 定时任务是真实发送，不是预演。
            ),
        )

    def _run_with_session(self, job_name: str, runner: Callable[[Session], dict]) -> None:  # 给定时任务提供数据库 Session。
        db = SessionLocal()  # 定时任务不是 HTTP 请求，不能用 Depends(get_db)，所以这里手动创建 Session。
        try:  # 捕获任务执行过程中的异常。
            logger.info("%s started.", job_name)  # 记录任务开始。
            result = runner(db)  # 执行业务逻辑，比如采集快照、计算热点、发送邮件。
            logger.info("%s finished: %s", job_name, self._summarize_result(result))  # 记录任务结果摘要。
        except Exception:  # 捕获所有异常，避免后台任务异常导致调度线程中断。
            logger.exception("%s failed.", job_name)  # 记录完整 traceback，方便排查。
        finally:  # 无论成功还是失败，都必须关闭数据库连接。
            db.close()  # 关闭 Session，把连接归还给连接池。

    def _summarize_result(self, result: dict) -> dict:  # 把业务返回值压缩成适合日志查看的小字典。
        keys = (  # 只保留这些关键字段，避免日志打印大量 ORM 对象。
            "job_id",  # 任务 id。
            "status",  # 任务状态。
            "total",  # 快照采集总数。
            "succeeded",  # 快照采集成功数。
            "failed",  # 快照采集失败数。
            "total_candidates",  # 热点候选数量。
            "generated",  # 生成热点数量。
            "report_id",  # 邮件日报 id。
            "subscriber_count",  # 收件人数量。
            "sent_count",  # 发送成功数量。
            "failed_count",  # 发送失败数量。
        )
        return {key: result.get(key) for key in keys if key in result}  # 只返回实际存在的字段。


scheduler_service = SchedulerService()  # 创建全局单例，main.py 启动和关闭时都使用同一个对象。
```

### 4. 修改 `app/main.py`

把当前 `app/main.py` 改成下面结构：

```python
from collections.abc import AsyncGenerator  # 用来标注 lifespan 这个异步生成器的返回类型。
from contextlib import asynccontextmanager  # FastAPI 推荐用它管理应用启动和关闭生命周期。

from fastapi import FastAPI  # FastAPI 是应用入口类。

from app.api.routes_email_digest import router as email_digest_router  # 邮件日报路由。
from app.api.routes_health import router as health_router  # 健康检查路由。
from app.api.routes_hot_projects import router as hot_projects_router  # 热点项目路由。
from app.api.routes_repositories import router as repositories_router  # 仓库管理路由。
from app.api.routes_star_snapshots import router as star_snapshots_router  # 星标快照路由。
from app.core.config import settings  # 应用配置。
from app.services.scheduler_service import scheduler_service  # 后台调度器服务。


@asynccontextmanager  # 把普通异步函数变成 FastAPI 可识别的生命周期管理器。
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:  # app 参数由 FastAPI 传入，这里主要用于生命周期挂钩。
    scheduler_service.start()  # 应用启动时启动调度器。
    try:  # yield 前是启动逻辑，yield 后是关闭逻辑。
        yield  # 服务运行期间停在这里，FastAPI 正常处理 HTTP 请求。
    finally:  # 应用关闭时一定会执行这里。
        scheduler_service.stop()  # 停止调度器，避免后台线程残留。


app = FastAPI(  # 创建 FastAPI 应用。
    title=settings.app_name,  # 应用名称。
    version=settings.app_version,  # 应用版本。
    docs_url="/docs",  # Swagger 文档地址。
    openapi_url="/openapi.json",  # OpenAPI JSON 地址。
    lifespan=lifespan,  # 绑定启动和关闭生命周期，让调度器跟随应用一起启动/停止。
)

app.include_router(health_router, prefix="/api/v1")  # 注册健康检查接口。
app.include_router(repositories_router, prefix="/api/v1")  # 注册仓库接口。
app.include_router(star_snapshots_router, prefix="/api/v1")  # 注册星标快照接口。
app.include_router(hot_projects_router, prefix="/api/v1")  # 注册热点项目接口。
app.include_router(email_digest_router, prefix="/api/v1")  # 注册邮件日报接口。


@app.get("/", include_in_schema=False)  # 根路径接口，不放进接口文档。
def root() -> dict[str, str]:  # 返回服务基础信息。
    return {  # 返回一个简单字典。
        "service": settings.app_name,  # 服务名称。
        "docs": "/docs",  # 文档地址。
        "health": "/api/v1/health",  # 健康检查地址。
    }
```

## Runtime Usage

### 1. 正常开发启动

```powershell
uvicorn app.main:app --reload
```

启动后日志里应该看到：

```text
Registered schedule star_snapshot_job with cron 0 * * * *.
Registered schedule hot_project_job with cron 30 8 * * *.
Registered schedule email_digest_job with cron 0 9 * * *.
Scheduler started.
```

### 2. 本地不想自动跑任务时

在 `.env` 里写：

```env
SCHEDULER_ENABLED=false
```

这样启动 FastAPI 时不会注册和执行后台任务，但手动接口仍然可用。

### 3. 临时测试调度是否触发

测试时可以临时把 `.env` 改成：

```env
SCHEDULER_ENABLED=true
STAR_SNAPSHOT_CRON=*/1 * * * *
HOT_PROJECT_CRON=*/2 * * * *
DIGEST_CRON=*/3 * * * *

SCHEDULER_ENABLED=true
STAR_SNAPSHOT_CRON=0 * * * *
HOT_PROJECT_CRON=30 8 * * *
DIGEST_CRON=0 9 * * *
```

含义：

```text
每 1 分钟采集一次快照
每 2 分钟计算一次热点
每 3 分钟发送一次日报
```

测试完成后必须恢复：

```env
STAR_SNAPSHOT_CRON=0 * * * *
HOT_PROJECT_CRON=30 8 * * *
DIGEST_CRON=0 9 * * *
```

## Test Plan

### 1. 安装依赖

```powershell
pip install -r requirements.txt
```

验证：

```powershell
python -c "from apscheduler.schedulers.background import BackgroundScheduler; print('ok')"
```

预期：

```text
ok
```

### 2. 语法检查

```powershell
python -m compileall app
```

预期：

```text
没有 SyntaxError
```

### 3. 启动服务检查

```powershell
uvicorn app.main:app --reload
```

预期：

```text
Scheduler started.
```

然后访问：

```text
GET http://127.0.0.1:8000/api/v1/health
```

预期：

```json
{
  "data": {
    "status": "ok"
  }
}
```

### 4. 自动执行检查

临时设置：

```env
STAR_SNAPSHOT_CRON=*/1 * * * *
HOT_PROJECT_CRON=*/2 * * * *
DIGEST_CRON=*/3 * * * *
```

观察日志：

```text
star_snapshot_job started.
star_snapshot_job finished: ...
hot_project_job started.
hot_project_job finished: ...
email_digest_job started.
email_digest_job finished: ...
```

### 5. 数据库检查

检查快照是否新增：

```sql
SELECT repository_id, stars, snapshot_at
FROM star_snapshots
ORDER BY snapshot_at DESC
LIMIT 5;
```

检查热点是否生成：

```sql
SELECT report_date, rank_no, repository_id, hot_score
FROM hot_projects
ORDER BY report_date DESC, rank_no ASC
LIMIT 10;
```

检查邮件日报是否生成：

```sql
SELECT report_date, subject, status, sent_at
FROM email_reports
ORDER BY created_at DESC
LIMIT 5;
```

检查邮件投递记录：

```sql
SELECT email, status, error_message, sent_at
FROM email_deliveries
ORDER BY created_at DESC
LIMIT 10;
```

## Assumptions

- 本阶段只做应用内调度，不引入 Celery、Redis、RabbitMQ。
- 本阶段使用 APScheduler 3.11.3，因为这是当前 pip 可安装的最新稳定版本。
- 本阶段使用单进程部署。如果以后用多个 `uvicorn workers`，每个 worker 都会启动一个调度器，可能导致重复采集和重复发邮件。
- 定时邮件任务默认是真实发送，即 `dry_run=False`。
- 如果本地调试不想自动发邮件，需要设置 `SCHEDULER_ENABLED=false`。
- 所有新增代码继续加详细中文注释，解释“这是什么”和“为什么这样写”。
