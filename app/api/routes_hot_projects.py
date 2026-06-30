from datetime import date  # date 用来声明查询参数 report_date。

from fastapi import APIRouter, Depends, Query, status  # APIRouter 定义路由；Depends 注入依赖；Query 定义查询参数；status 提供状态码。
from sqlalchemy.orm import Session  # Session 用来标注数据库会话类型。

from app.db.session import get_db  # get_db 为每次请求提供数据库会话。
from app.schemas.hot_project import HotProjectCalculateRequest, HotProjectResponse, HotProjectRunResponse  # 导入请求体和响应体。
from app.services.hot_project_service import HotProjectService  # 导入热点项目业务服务。


router = APIRouter(prefix="/hot-projects", tags=["hot_projects"])  # 当前文件的接口统一以 /hot-projects 开头。


@router.post("/runs", response_model=HotProjectRunResponse, status_code=status.HTTP_201_CREATED)  # POST /hot-projects/runs 手动计算热点榜。
def calculate_hot_projects(payload: HotProjectCalculateRequest, db: Session = Depends(get_db)) -> dict:  # 接收请求体和数据库会话。
    service = HotProjectService(db)  # 创建业务服务对象。
    return service.calculate_hot_projects(payload.report_date, payload.top_n, payload.include_disabled)  # 执行热点计算。


@router.get("", response_model=list[HotProjectResponse])  # GET /hot-projects 查询热点榜单。
def list_hot_projects(  # 定义热点榜单查询接口。
    report_date: date | None = Query(default=None, description="榜单日期；不传则查询今天。"),  # 可选查询日期。
    limit: int = Query(default=20, ge=1, le=100, description="返回数量，范围 1-100。"),  # 限制返回数量。
    db: Session = Depends(get_db),  # 注入数据库会话。
) -> list[dict]:  # 返回热点项目列表。
    service = HotProjectService(db)  # 创建业务服务对象。
    return service.list_hot_projects(report_date, limit)  # 查询并返回热点榜单。