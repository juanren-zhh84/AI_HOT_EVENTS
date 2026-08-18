# app/api/routes_config.py
"""
配置管理接口。

路径前缀 /admin/configs，最终完整路径：
GET    /api/v1/admin/configs            获取分组配置（敏感字段脱敏）
PUT    /api/v1/admin/configs            批量更新配置并热生效
POST   /api/v1/admin/configs/test-email 发送测试邮件
POST   /api/v1/admin/configs/test-llm   测试大模型连通性

全部接口需要管理 token（Authorization: Bearer xxx）。
"""

from fastapi import APIRouter, Depends, HTTPException  # 路由、依赖注入、异常。
from sqlalchemy.orm import Session  # 数据库会话类型。
from starlette import status  # HTTP 状态码。

from app.api.dependencies import require_admin_token  # 管理接口鉴权依赖。
from app.db.session import get_db  # 数据库会话依赖。
from app.schemas.config import ConfigUpdateRequest, TestEmailRequest  # 请求体模型。
from app.services.config_service import ConfigService  # 配置服务。

router = APIRouter(  # 创建路由。
    prefix="/admin/configs",  # 接口前缀。
    tags=["admin-config"],  # Swagger 分组名。
    dependencies=[Depends(require_admin_token)],  # 整个路由组都需要管理 token。
)  # 路由创建结束。


@router.get("")  # GET /api/v1/admin/configs。
def list_configs(db: Session = Depends(get_db)) -> dict:  # 获取分组配置。
    """返回分组配置（敏感字段脱敏）和系统只读信息。"""
    return ConfigService(db).list_configs()  # 交给配置服务处理。


@router.put("")  # PUT /api/v1/admin/configs。
def update_configs(payload: ConfigUpdateRequest, db: Session = Depends(get_db)) -> dict:  # 批量更新配置。
    """批量更新配置，保存后立即热生效。"""
    service = ConfigService(db)  # 创建配置服务。
    result = service.update_configs(payload.updates)  # 先更新数据库。
    if result["errors"]:  # 如果有字段校验失败。
        raise HTTPException(  # 返回 400，detail 里带 updated/errors，方便前端提示。
            status_code=status.HTTP_400_BAD_REQUEST,  # 400 状态码。
            detail=result,  # 失败详情：哪些字段失败、为什么。
        )  # 异常结束。
    apply_result = service.apply()  # 全部成功才热生效：更新 settings + 重载调度器。
    return {"updated": result["updated"], **apply_result}  # 返回更新结果和生效结果。


@router.post("/test-email")  # POST /api/v1/admin/configs/test-email。
def test_email(payload: TestEmailRequest, db: Session = Depends(get_db)) -> dict:  # 发送测试邮件。
    """用当前生效的 SMTP 配置发一封测试邮件。"""
    if "@" not in payload.to_email:  # 简单校验邮箱格式。
        raise HTTPException(status_code=422, detail="to_email 不合法")  # 返回参数错误。
    return ConfigService(db).test_email(payload.to_email)  # 交给配置服务。


@router.post("/test-llm")  # POST /api/v1/admin/configs/test-llm。
def test_llm(db: Session = Depends(get_db)) -> dict:  # 测试大模型连通性。
    """用当前生效的 LLM 配置调用一次最小请求。"""
    return ConfigService(db).test_llm()  # 交给配置服务。