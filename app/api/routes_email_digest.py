
from fastapi import APIRouter, Depends, status  # APIRouter 定义路由；Depends 注入依赖；status 提供状态码。
from sqlalchemy.orm import Session  # Session 用来标注数据库会话类型。

from app.db.models import Subscriber
from app.db.session import get_db  # get_db 为每次请求提供数据库会话。
from app.schemas.email_digest import EmailDigestRunRequest, EmailDigestRunResponse, SubscriberCreate, SubscriberResponse  # 导入请求体和响应体。
from app.services.email_digest_service import EmailDigestService  # 导入邮件日报业务服务。


router = APIRouter(prefix="/email-digests", tags=["email_digests"])  # 当前文件接口统一以 /email-digests 开头。


@router.post("/subscribers", response_model=SubscriberResponse, status_code=status.HTTP_201_CREATED)  # POST /email-digests/subscribers 新增订阅者。
def create_subscriber(payload: SubscriberCreate, db: Session = Depends(get_db)) -> Subscriber:  # 接收请求体和数据库会话。
    service = EmailDigestService(db)  # 创建业务服务对象。
    return service.create_subscriber(str(payload.email), payload.name)  # 创建订阅者并返回。


@router.get("/subscribers", response_model=list[SubscriberResponse])  # GET /email-digests/subscribers 查询订阅者列表。
def list_subscribers(db: Session = Depends(get_db)) -> list[Subscriber]:  # 注入数据库会话。
    service = EmailDigestService(db)  # 创建业务服务对象。
    return service.list_subscribers()  # 返回订阅者列表。


@router.post("/runs", response_model=EmailDigestRunResponse, status_code=status.HTTP_201_CREATED)  # POST /email-digests/runs 手动生成/发送日报。
def run_email_digest(payload: EmailDigestRunRequest, db: Session = Depends(get_db)) -> dict:  # 接收请求体和数据库会话。
    service = EmailDigestService(db)  # 创建业务服务对象。
    return service.run_digest(payload.report_date, payload.top_n, payload.dry_run)  # 执行日报生成/发送。