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