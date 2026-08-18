# app/core/config.py
"""
应用配置。

本文件承担三层角色：
1. 启动引导配置源：从 .env（服务器为 .env.production）读取 DATABASE_URL、API_AUTH_TOKEN 等启动必需配置。
2. 默认值兜底层：DEFAULT_CONFIGS 里各项的默认值都来自 Settings 字段，用于首次初始化 app_configs 表。
3. 内存生效单例：运行时配置由 ConfigService 写入 settings 单例，实现页面修改后热生效。

配置读取顺序：.env（Settings 加载）-> app_configs 表（启动时覆盖）-> settings 单例（运行时内存）。
"""

from collections.abc import Callable  # 类型标注：DEFAULT_CONFIGS 的默认值取值函数。
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI_Hot_Events"
    app_version: str = "0.1.0"
    app_env: str = "local"
    debug: bool = False
    timezone: str = "Asia/Shanghai"

    database_url: str
    api_auth_token: str | None = None
    github_token: str | None = None

    github_api_base_url: str = "https://api.github.com"
    github_api_version: str = "2022-11-28"

    smtp_host: str | None = None
    smtp_port: int = 465
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_ssl: bool = True
    smtp_use_tls: bool = False
    mail_from: str | None = None
    mail_from_name: str = "GitHub 热点项目日报"

    llm_enabled: bool = False  # 是否启用大模型生成中文画像；False 时走本地规则兜底。
    llm_provider: str = "deepseek"  # 当前大模型供应商名称，仅用于日志和排查，不参与业务判断。
    llm_api_base_url: str = "https://api.deepseek.com"  # OpenAI-compatible API 地址，DeepSeek 默认使用这个地址。
    llm_api_key: str | None = None  # 大模型 API Key，只从 .env 读取，不能写死到代码里。
    llm_model: str = "deepseek-v4-flash"  # 默认使用 DeepSeek V4 Flash，避免使用即将弃用的旧模型名。
    llm_timeout_seconds: int = 60  # 大模型请求超时时间，避免接口长时间卡住定时任务。
    llm_temperature: float = 0.2  # 中文摘要需要稳定输出，温度保持较低。

    star_snapshot_cron: str = "0 * * * *"
    hot_project_cron: str = "30 8 * * *"
    digest_cron: str = "0 9 * * *"
    discovery_cron: str = "0 */6 * * *"
    profile_refresh_cron: str = "0 2 * * *"
    hot_project_top_n: int = 20
    scheduler_enabled: bool = True  # 是否启用后台调度器；本地调试不想自动跑任务时，可以在 .env 里设为 false。

    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()


# ===== 运行时可管理配置清单（新增部分） =====
# 这份清单是"配置元数据注册表"：描述哪些配置可以放进 app_configs 表由页面管理。
# 每项：(key, category, value_type, is_secret, description, default_getter)
# - key：配置名，与 Settings 字段名一一对应（key 全小写就是 settings 的属性名）。
# - default_getter：从 Settings 读取默认值，用于首次初始化 app_configs 表；后续以数据库为准。
# 新增可管理配置时，只需在这里加一行，同时给 Settings 补一个字段，不需要改 service。
DEFAULT_CONFIGS: tuple[tuple[str, str, str, bool, str, Callable[[Settings], object]], ...] = (
    ("GITHUB_TOKEN", "github", "str", True, "GitHub API Token，用于采集仓库数据", lambda s: s.github_token),
    ("GITHUB_API_BASE_URL", "github", "str", False, "GitHub API 地址", lambda s: s.github_api_base_url),
    ("GITHUB_API_VERSION", "github", "str", False, "GitHub API 版本", lambda s: s.github_api_version),
    ("SMTP_HOST", "smtp", "str", False, "SMTP 服务器地址", lambda s: s.smtp_host),
    ("SMTP_PORT", "smtp", "int", False, "SMTP 端口（SSL 默认 465）", lambda s: s.smtp_port),
    ("SMTP_USERNAME", "smtp", "str", False, "SMTP 用户名（邮箱地址）", lambda s: s.smtp_username),
    ("SMTP_PASSWORD", "smtp", "str", True, "SMTP 密码或授权码", lambda s: s.smtp_password),
    ("SMTP_USE_SSL", "smtp", "bool", False, "使用 SSL 连接（465 端口）", lambda s: s.smtp_use_ssl),
    ("SMTP_USE_TLS", "smtp", "bool", False, "使用 TLS 连接（587 端口）", lambda s: s.smtp_use_tls),
    ("MAIL_FROM", "smtp", "str", False, "发件人邮箱", lambda s: s.mail_from),
    ("MAIL_FROM_NAME", "smtp", "str", False, "发件人展示名称", lambda s: s.mail_from_name),
    ("LLM_ENABLED", "llm", "bool", False, "是否启用大模型生成中文画像", lambda s: s.llm_enabled),
    ("LLM_PROVIDER", "llm", "str", False, "大模型供应商名称（仅日志用）", lambda s: s.llm_provider),
    ("LLM_API_BASE_URL", "llm", "str", False, "OpenAI-compatible API 地址", lambda s: s.llm_api_base_url),
    ("LLM_API_KEY", "llm", "str", True, "大模型 API Key", lambda s: s.llm_api_key),
    ("LLM_MODEL", "llm", "str", False, "模型名，例如 deepseek-v4-flash", lambda s: s.llm_model),
    ("LLM_TIMEOUT_SECONDS", "llm", "int", False, "大模型请求超时（秒）", lambda s: s.llm_timeout_seconds),
    ("LLM_TEMPERATURE", "llm", "float", False, "采样温度（低更稳定）", lambda s: s.llm_temperature),
    ("HOT_PROJECT_TOP_N", "hot", "int", False, "热点榜 Top N", lambda s: s.hot_project_top_n),
    ("SCHEDULER_ENABLED", "scheduler", "bool", False, "调度器总开关", lambda s: s.scheduler_enabled),
)