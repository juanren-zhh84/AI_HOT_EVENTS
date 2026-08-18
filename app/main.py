from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI  # FastAPI 是应用入口类。
from starlette.responses import FileResponse, HTMLResponse
from starlette.staticfiles import StaticFiles

from app.core.config import settings  # 应用配置。
from app.api.routes_health import router as health_router  # 健康检查路由。
from app.api.routes_repositories import router as repositories_router  # 仓库管理路由。
from app.api.routes_star_snapshots import router as star_snapshots_router  # 星标快照路由。
from app.api.routes_hot_projects import router as hot_projects_router  # 热点项目路由。
from app.api.routes_email_digest import router as email_digest_router  # 邮件日报路由。
from app.services.scheduler_service import scheduler_service  # 后台调度器服务。
from app.api.routes_monitor_sources import router as monitor_sources_router  # 监控源路由。
from app.api.routes_discovery import router as discovery_router  # 导入自动发现路由。
from app.api.routes_project_profiles import router as project_profiles_router  # 导入项目画像路由。
from app.api.routes_schedules import router as schedules_router  # 导入调度配置管理路由。
from app.api.routes_jobs import router as jobs_router  # 导入任务查询路由。
from app.api.routes_github import router as github_router  # 导入 GitHub 运维路由。
from app.api.routes_config import router as config_router

BASE_DIR = Path(__file__).resolve().parent.parent  # app/ 的上一级目录，即项目根目录。
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"  # Vue 前端构建产物目录。

import logging  # 标准日志库，启动日志和 uvicorn 日志保持一致。
logger = logging.getLogger("uvicorn.error")  # 使用 uvicorn 日志器，方便在 PyCharm 和服务器日志中查看。


@asynccontextmanager  # 把普通异步函数变成 FastAPI 可识别的生命周期管理器。
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    # 启动时把数据库里的运行时配置合并进 settings 单例，覆盖 .env 的默认值。
    from app.db.session import SessionLocal  # 数据库会话工厂（延迟导入，避免循环依赖）。
    from app.services.config_service import ConfigService  # 配置服务（延迟导入）。
    db = SessionLocal()  # 创建数据库会话。
    try:  # 确保会话最终关闭。
        load_result = ConfigService(db).load_into_settings()  # 加载数据库配置。
        logger.info("已从 app_configs 加载 %s 项运行时配置。", load_result["applied"])  # 输出启动日志。
    finally:  # 不管成功失败。
        db.close()  # 关闭会话。

    scheduler_service.start()  # 启动调度器（配置加载完成后才启动）。
    try:  # 应用运行期间。
        yield  # yield 前是启动逻辑，yield 后是关闭逻辑。
    finally:  # 应用关闭时。
        scheduler_service.stop()  # 停止调度器。


app = FastAPI(  # 创建 FastAPI 应用。
    title=settings.app_name,  # 应用名称。
    version=settings.app_version,  # 应用版本。
    docs_url="/docs",  # Swagger 文档地址。
    openapi_url="/openapi.json",  # OpenAPI JSON 地址。
    lifespan=lifespan,  # 绑定启动/关闭生命周期。
)

app.include_router(health_router, prefix="/api/v1")  # 注册健康检查接口。
app.include_router(repositories_router, prefix="/api/v1")  # 注册仓库接口。
app.include_router(star_snapshots_router, prefix="/api/v1")  # 注册星标快照接口。
app.include_router(hot_projects_router, prefix="/api/v1")  # 注册热点项目接口。
app.include_router(email_digest_router, prefix="/api/v1")  # 注册邮件日报接口。
app.include_router(monitor_sources_router, prefix="/api/v1")  # 注册监控源接口。
app.include_router(discovery_router, prefix="/api/v1")  # 注册自动发现接口。
app.include_router(project_profiles_router, prefix="/api/v1")  # 注册项目画像接口。
app.include_router(schedules_router, prefix="/api/v1")  # 注册调度配置接口。
app.include_router(jobs_router, prefix="/api/v1")  # 注册任务查询接口。
app.include_router(github_router, prefix="/api/v1")  # 注册 GitHub 运维接口。
app.include_router(config_router, prefix="/api/v1")  # 注册配置管理接口（本次新增）。

if FRONTEND_DIST.exists():  # 前端已构建时才挂载静态资源。
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")  # Vite 构建产物里的 /assets 目录。


@app.get("/admin", include_in_schema=False)
def admin_page():  # 返回前端页面。
    index_file = FRONTEND_DIST / "index.html"  # 前端入口文件。
    if not index_file.exists():  # 前端还没构建。
        return HTMLResponse(  # 返回构建提示页。
            "<h3>前端尚未构建</h3>"
            "<p>请先执行: <code>cd frontend && npm install && npm run build</code></p>",
            status_code=503,  # 503 表示服务暂时不可用。
        )  # 提示页结束。
    return FileResponse(index_file)  # 返回前端页面。


@app.get("/", include_in_schema=False)  # 根路径接口，不放进接口文档。
def root() -> dict[str, str]:  # 返回服务基础信息。
    return {  # 返回一个简单字典。
        "service": settings.app_name,  # 服务名称。
        "docs": "/docs",  # 文档地址。
        "health": "/api/v1/health",  # 健康检查地址。
        "admin": "/admin",  # 后台管理页面地址。
    }