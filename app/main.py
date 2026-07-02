from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI  # FastAPI 是应用入口类。
from app.core.config import settings  # 应用配置。
from app.api.routes_health import router as health_router  # 健康检查路由。
from app.api.routes_repositories import router as repositories_router  # 仓库管理路由。
from app.api.routes_star_snapshots import router as star_snapshots_router  # 星标快照路由。
from app.api.routes_hot_projects import router as hot_projects_router  # 热点项目路由。
from app.api.routes_email_digest import router as email_digest_router  # 邮件日报路由。
from app.services.scheduler_service import scheduler_service  # 后台调度器服务。

@asynccontextmanager # 把普通异步函数变成 FastAPI 可识别的生命周期管理器
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    scheduler_service.start()
    try:
        yield # yield 前是启动逻辑，yield 后是关闭逻辑。
    finally:
        scheduler_service.stop()


app = FastAPI(  # 创建 FastAPI 应用。
    title=settings.app_name,  # 应用名称。
    version=settings.app_version,  # 应用版本。
    docs_url="/docs",  # Swagger 文档地址。
    openapi_url="/openapi.json",  # OpenAPI JSON 地址。
    lifespan=lifespan # 绑定启动/关闭生命周期，让调度器跟随应用一起启动/停止
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