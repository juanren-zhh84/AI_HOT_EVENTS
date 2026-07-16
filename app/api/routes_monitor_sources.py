from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin_token
from app.db.models import MonitorSource
from app.db.session import get_db
from app.schemas.monitor_source import MonitorSourceResponse, MonitorSourceCreate, MonitorSourceUpdate
from app.services.monitor_source_service import MonitorSourceService

router = APIRouter(
    prefix="/monitor-sources",  # 当前文件所有接口统一以 /monitor-sources 开头。
    tags=["monitor-sources"],  # Swagger 文档里归到 monitor-sources 分组。
    dependencies=[Depends(require_admin_token)],  # 监控源是管理配置，整组接口都需要管理 token。
)

# POST /monitor-sources 创建监控源。
@router.post("",response_model=MonitorSourceResponse, status_code=status.HTTP_201_CREATED)
def create_monitor_source(pyload: MonitorSourceCreate, db: Session = Depends(get_db)) -> MonitorSource:
    """接收请求体和数据库会话"""
    service = MonitorSourceService(db)
    return service.create_source(pyload) # 调用service创建监控资源并返回

# GET /monitor-sources 查询监控源列表。
@router.get("", response_model=list[MonitorSourceResponse])
def list_monitor_sources(db: Session = Depends(get_db)) -> list[MonitorSourceResponse]:  # 只需要数据库会话。
    service = MonitorSourceService(db)  # 创建业务服务对象。
    return service.list_sources()  # 返回所有监控源。

# GET /monitor-sources/{source_id} 查询单个监控源。
@router.get("/{source_id}", response_model=MonitorSourceResponse)
def get_monitor_source(source_id: str, db: Session = Depends(get_db)) -> MonitorSourceResponse:  # 接收路径参数和数据库会话。
    service = MonitorSourceService(db)  # 创建业务服务对象。
    source = service.get_source(source_id)  # 查询监控源。
    if not source:  # 如果查不到。
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitor source not found")  # 返回 404。
    return source  # 返回查询结果。

# PATCH /monitor-sources/{source_id} 更新监控源。
@router.patch("/{source_id}", response_model=MonitorSourceResponse)
def update_monitor_source(source_id: str, payload: MonitorSourceUpdate, db: Session = Depends(get_db)) -> MonitorSourceResponse:  # 接收路径参数、请求体和数据库会话。
    service = MonitorSourceService(db)  # 创建业务服务对象。
    source = service.update_source(source_id, payload)  # 调用更新逻辑。
    if not source:  # 如果查不到。
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitor source not found")  # 返回 404。
    return source  # 返回更新后的监控源。