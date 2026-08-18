# app/schemas/config.py
"""
配置管理接口的请求体模型。

和项目的其他 schemas 文件一样，只负责定义接口请求/响应的数据结构。
"""

from pydantic import BaseModel  # 用来定义请求体模型。


class ConfigUpdateRequest(BaseModel):  # 批量更新配置请求体。
    """批量更新运行时配置。"""

    updates: dict[str, str]  # 配置 key -> 新值；敏感字段传空字符串表示"不修改"。


class TestEmailRequest(BaseModel):  # 测试邮件请求体。
    """给指定邮箱发送一封测试邮件。"""

    to_email: str  # 接收测试邮件的邮箱地址。