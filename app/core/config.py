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
