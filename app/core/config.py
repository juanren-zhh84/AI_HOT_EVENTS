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

    discovery_cron: str = "0 */6 * * *"
    star_snapshot_cron: str = "0 * * * *"
    profile_refresh_cron: str = "0 2 * * *"
    hot_project_cron: str = "30 8 * * *"
    digest_cron: str = "0 9 * * *"
    hot_project_top_n: int = 20

    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
