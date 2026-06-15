from datetime import UTC, datetime

from fastapi import APIRouter, Response, status

from app.core.config import settings
from app.db.session import check_database_connection


router = APIRouter(tags=["health"])


@router.get("/health")
def health(response: Response) -> dict:
    dependencies = {
        "database": "ok" if check_database_connection() else "error",
    }
    service_ok = all(value == "ok" for value in dependencies.values())

    if not service_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "data": {
            "status": "ok" if service_ok else "degraded",
            "version": settings.app_version,
            "time": datetime.now(UTC).isoformat(),
            "dependencies": dependencies,
        }
    }
