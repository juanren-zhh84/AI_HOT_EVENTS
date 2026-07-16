from fastapi import Header,HTTPException,status
from app.core.config import settings


def require_admin_token(authorization: str | None = Header(default=None)) -> None:
    """
    校验管理接口 Bearer Token 是否有效
    本地没配置 API_AUTH_TOKEN 时允许访问，方便学习和调试。
    只要配置了 API_AUTH_TOKEN，就必须带 Authorization: Bearer xxx。
    """
    if not settings.api_auth_token:
        return

    expected = f"Bearer {settings.api_auth_token}"
    # 如果请求头不匹配
    if authorization != expected:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail = "admin token丢失或无效"
        )