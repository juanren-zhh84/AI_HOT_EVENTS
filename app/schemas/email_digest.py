from datetime import date, datetime  # date 表示日报日期；datetime 表示生成/发送时间。
from pydantic import BaseModel, EmailStr, Field  # BaseModel 定义模型；EmailStr 校验邮箱格式；Field 写说明。


class SubscriberCreate(BaseModel):  # 新增订阅者请求体。
    """新增订阅者请求体。"""
    email: EmailStr = Field(..., description="订阅者邮箱。")  # 邮箱必填，并自动校验格式。
    name: str | None = Field(default=None, description="订阅者名称，可为空。")  # 名称可选。


class SubscriberResponse(BaseModel):  # 订阅者响应体。
    """订阅者响应体。"""
    id: str  # 订阅者 id。
    email: str  # 订阅者邮箱。
    name: str | None = None  # 订阅者名称。
    status: str  # 订阅状态。
    created_at: datetime  # 创建时间。
    model_config = {"from_attributes": True}  # 允许从 SQLAlchemy ORM 对象直接转换。


class EmailDigestRunRequest(BaseModel):  # 手动发送日报请求体。
    """手动发送邮件日报请求体。"""
    report_date: date | None = Field(default=None, description="日报日期；不传则发送今天的热点榜。")  # 不传默认今天。
    top_n: int = Field(default=20, ge=1, le=100, description="邮件里展示前 N 个热点项目。")  # 控制邮件内容数量。
    dry_run: bool = Field(default=False, description="是否只生成报告不发送邮件。")  # True 时只生成 email_reports，不发送。


class EmailDeliveryResponse(BaseModel):  # 单条投递记录响应体。
    """邮件投递记录响应体。"""
    id: str  # 投递记录 id。
    email: str  # 实际发送邮箱。
    status: str  # 发送状态。
    error_message: str | None = None  # 失败原因。
    sent_at: datetime | None = None  # 发送时间。
    model_config = {"from_attributes": True}  # 允许从 ORM 对象转换。


class EmailDigestRunResponse(BaseModel):  # 手动发送日报响应体。
    """邮件日报发送结果响应体。"""
    report_id: str  # email_reports 表 id。
    report_date: date  # 日报日期。
    subject: str  # 邮件标题。
    status: str  # 报告状态。
    subscriber_count: int  # 目标订阅者数量。
    sent_count: int  # 成功发送数量。
    failed_count: int  # 失败数量。
    dry_run: bool  # 是否为只生成不发送。
    deliveries: list[EmailDeliveryResponse]  # 投递记录列表。