from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.services.discovery_service import DiscoveryService
from app.api.dependencies import require_admin_token
from app.db.session import get_db
from app.schemas.discovery import DiscoveryRunResponse, DiscoveryRunRequest

router = APIRouter(prefix="/discovery",tags=["discovery"]) # 当前文件接口统一以 /discovery 开头。

@router.post("/runs",response_model=DiscoveryRunResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin_token)])
def run_discovery(payload: DiscoveryRunRequest, db: Session = Depends(get_db)) -> dict:
    service = DiscoveryService(db)
    return service.run_discovery(payload)