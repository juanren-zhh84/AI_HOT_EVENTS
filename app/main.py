from fastapi import FastAPI

from app.api.routes_health import router as health_router
from app.core.config import settings


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url="/docs",
    openapi_url="/openapi.json",
)

app.include_router(health_router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {
        "service": settings.app_name,
        "docs": "/docs",
        "health": "/api/v1/health",
    }
