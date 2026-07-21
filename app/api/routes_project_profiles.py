from fastapi import APIRouter, status, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin_token
from app.db.session import get_db
from app.schemas.project_profile import ProjectProfileGenerateRequest, ProjectProfileResponse
from app.services.project_profile_service import ProjectProfileService

router = APIRouter(prefix="/project-profiles", tags=["project_profiles"])  # 当前文件接口统一以 /project-profiles 开头。

@router.post("/runs", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin_token)])  # POST /project-profiles/runs 手动生成画像。
def run_project_profiles(payload: ProjectProfileGenerateRequest, db: Session = Depends(get_db)) -> dict:  # 接收请求体和数据库会话。
    service = ProjectProfileService(db)  # 创建业务服务对象。
    return service.run_profile_generation(payload)  # 执行画像生成任务。


@router.get("/repositories/{repository_id}", response_model=ProjectProfileResponse)  # GET /project-profiles/repositories/{repository_id} 查询画像。
def get_project_profile(repository_id: str, db: Session = Depends(get_db)) -> ProjectProfileResponse:  # 接收仓库 id。
    service = ProjectProfileService(db)  # 创建业务服务对象。
    profile = service.get_profile(repository_id)  # 查询画像。
    if not profile:  # 如果没有画像。
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project profile not found")  # 返回 404。
    return profile  # 返回画像。
