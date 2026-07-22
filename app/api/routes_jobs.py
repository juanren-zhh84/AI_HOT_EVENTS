from typing import List, Type

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin_token
from app.db.models import Job
from app.db.session import get_db
from app.schemas.job import JobResponse

router = APIRouter(prefix="/jobs", tags=["jobs"], dependencies=[Depends(require_admin_token)])  # 当前文件接口统一以 /jobs 开头。


@router.get("", response_model=list[JobResponse])  # GET /jobs 查询任务列表。
def list_jobs(  # 定义任务列表接口。
    limit: int = Query(default=50, ge=1, le=200, description="返回任务数量"),  # 限制返回数量，避免一次返回过多记录。
    db: Session = Depends(get_db),  # 注入数据库会话。
) -> list[Type[Job]]:  # 返回任务 ORM 列表。
    return db.query(Job).order_by(Job.created_at.desc()).limit(limit).all()  # 按创建时间倒序查询最近任务。