# app/api/routes_repositories.py  # 这个文件只定义 HTTP 接口，不直接写复杂业务。

from fastapi import APIRouter, Depends, HTTPException, status  # APIRouter 定义路由，Depends 注入依赖，HTTPException 返回错误。
from sqlalchemy.orm import Session  # Session 用于类型标注数据库会话。

from app.db.session import get_db  # get_db 为每个请求提供数据库会话。
from app.schemas.repository import RepositoryCreate, RepositoryResponse, RepositoryUpdate  # 导入请求体和响应体模型。
from app.services.repository_service import RepositoryService  # 导入仓库业务服务。


router = APIRouter(prefix="/repositories", tags=["repositories"])  # 当前文件所有接口统一以 /repositories 开头。


@router.post("", response_model=RepositoryResponse, status_code=status.HTTP_201_CREATED)  # POST /repositories 创建仓库。
def create_repository(payload: RepositoryCreate, db: Session = Depends(get_db)) -> RepositoryResponse:  # 接收请求体和数据库会话。
    service = RepositoryService(db)  # 创建业务服务。
    try:  # 创建仓库可能出现业务错误。
        return service.create_repository(payload.full_name, payload.source, payload.tags, payload.enabled)  # 调用 service 完成创建。
    except ValueError as exc:  # 捕获 full_name 格式错误或 GitHub 404。
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc  # 转成 HTTP 400。


@router.get("", response_model=list[RepositoryResponse])  # GET /repositories 查询列表。
def list_repositories(db: Session = Depends(get_db)) -> list[RepositoryResponse]:  # 注入数据库会话。
    service = RepositoryService(db)  # 创建业务服务。
    return service.list_repositories()  # 返回仓库列表。


@router.get("/{repository_id}", response_model=RepositoryResponse)  # GET /repositories/{repository_id} 查询详情。
def get_repository(repository_id: str, db: Session = Depends(get_db)) -> RepositoryResponse:  # 接收路径参数和数据库会话。
    service = RepositoryService(db)  # 创建业务服务。
    repository = service.get_repository(repository_id)  # 查询仓库。
    if not repository:  # 查不到时。
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")  # 返回 404。
    return repository  # 返回仓库对象。


@router.patch("/{repository_id}", response_model=RepositoryResponse)  # PATCH /repositories/{repository_id} 更新配置。
def update_repository(repository_id: str, payload: RepositoryUpdate, db: Session = Depends(get_db)) -> RepositoryResponse:  # 接收路径参数、请求体和数据库会话。
    service = RepositoryService(db)  # 创建业务服务。
    repository = service.update_repository(repository_id, payload.enabled, payload.tags)  # 更新仓库配置。
    if not repository:  # 查不到时。
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")  # 返回 404。
    return repository  # 返回更新后的仓库对象。