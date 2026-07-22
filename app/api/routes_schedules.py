from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from starlette import status

from app.api.dependencies import require_admin_token
from app.db.models import Schedule
from app.db.session import get_db
from app.schemas.schedule import ScheduleResponse, ScheduleUpdate, ScheduleReloadResponse
from app.services.schedule_service import ScheduleService
from app.services.scheduler_service import scheduler_service

router = APIRouter(prefix="/schedules", tags=["schedules"], dependencies=[Depends(require_admin_token)])  # 当前文件接口统一以 /schedules 开头。


@router.get("", response_model=list[ScheduleResponse])  # GET /schedules 查询全部调度配置。
def list_schedules(db: Session = Depends(get_db)) -> list[Schedule]:  # 注入数据库会话。
    service = ScheduleService(db)  # 创建调度配置服务。
    service.seed_default_schedules()  # 确保首次查询时默认调度已经存在。
    return service.list_schedules()  # 返回全部调度配置。


@router.get("/{schedule_id}", response_model=ScheduleResponse)  # GET /schedules/{schedule_id} 查询单个调度。
def get_schedule(schedule_id: str, db: Session = Depends(get_db)) -> Schedule:  # 接收调度 id 和数据库会话。
    service = ScheduleService(db)  # 创建调度配置服务。
    schedule = service.get_schedule(schedule_id)  # 查询调度配置。
    if schedule is None:  # 如果调度不存在。
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="schedule 不存在")  # 返回 404。
    return schedule  # 返回调度配置。


@router.patch("/{schedule_id}", response_model=ScheduleResponse)  # PATCH /schedules/{schedule_id} 更新调度配置。
def update_schedule(schedule_id: str, payload: ScheduleUpdate, db: Session = Depends(get_db)) -> Schedule:  # 接收调度 id、请求体和数据库会话。
    service = ScheduleService(db)  # 创建调度配置服务。
    schedule = service.update_schedule(schedule_id, payload)  # 更新 schedules 表。
    if schedule is None:  # 如果调度不存在。
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="schedule 不存在")  # 返回 404。
    scheduler_service.reload()  # 更新后重新加载 APScheduler，让新 cron 生效。
    return schedule  # 返回更新后的调度。


@router.post("/{schedule_id}/enable", response_model=ScheduleResponse)  # POST /schedules/{schedule_id}/enable 启用调度。
def enable_schedule(schedule_id: str, db: Session = Depends(get_db)) -> Schedule:  # 接收调度 id 和数据库会话。
    service = ScheduleService(db)  # 创建调度配置服务。
    schedule = service.enable_schedule(schedule_id)  # 启用调度。
    if schedule is None:  # 如果调度不存在。
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="schedule 不存在")  # 返回 404。
    scheduler_service.reload()  # 启用后重新加载 APScheduler。
    return schedule  # 返回启用后的调度。


@router.post("/{schedule_id}/disable", response_model=ScheduleResponse)  # POST /schedules/{schedule_id}/disable 禁用调度。
def disable_schedule(schedule_id: str, db: Session = Depends(get_db)) -> Schedule:  # 接收调度 id 和数据库会话。
    service = ScheduleService(db)  # 创建调度配置服务。
    schedule = service.disable_schedule(schedule_id)  # 禁用调度。
    if schedule is None:  # 如果调度不存在。
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="schedule 不存在")  # 返回 404。
    scheduler_service.reload()  # 禁用后重新加载 APScheduler，确保任务不再触发。
    return schedule  # 返回禁用后的调度。


@router.post("/reload", response_model=ScheduleReloadResponse)  # POST /schedules/reload 手动重新加载调度器。
def reload_schedules() -> dict:  # 不需要数据库会话，因为 SchedulerService 内部会自己创建 Session。
    return scheduler_service.reload()  # 重新加载 APScheduler 并返回注册结果。