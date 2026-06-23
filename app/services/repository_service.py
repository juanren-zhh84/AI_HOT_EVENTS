# app/services/repository_service.py  # 这个文件只处理业务，不直接定义 HTTP 接口。

from datetime import UTC, datetime  # UTC 用来统一保存时间；datetime 用来转换 GitHub 时间字符串。

import httpx  # 用来捕获 GitHubClient 请求 GitHub 时抛出的 HTTP 错误。
from sqlalchemy import select  # SQLAlchemy 2.x 推荐用 select 构造查询。
from sqlalchemy.orm import Session  # Session 是数据库会话类型。

from app.db.models import Repository  # Repository 是 repositories 表的 ORM 模型。
from app.services.github_client import GitHubClient  # GitHubClient 负责访问 GitHub API。


def parse_github_datetime(value: str | None) -> datetime | None:  # 把 GitHub 时间字符串转成 datetime。
    if not value:  # GitHub 某些时间字段可能为空。
        return None  # 为空时直接返回 None，数据库也保存为空。
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)  # GitHub 的 Z 表示 UTC，这里转成 Python datetime。


class RepositoryService:  # 仓库业务服务。
    def __init__(self, db: Session) -> None:  # 初始化时传入数据库会话。
        self.db = db  # 保存数据库会话，后面查询、插入、更新都用它。
        self.github_client = GitHubClient()  # 创建 GitHub 客户端，后面拉取仓库详情。

    def create_repository(self, full_name: str, source: str = "manual", tags: list[str] | None = None, enabled: bool = True) -> Repository:  # 创建仓库。
        owner, repo = self._parse_full_name(full_name)  # 校验并拆分 owner/repo。

        existing_repository = self.get_by_full_name(full_name)  # 先查重，避免重复插入。
        if existing_repository:  # 如果数据库里已经存在。
            return existing_repository  # 直接返回已有记录，让接口具备幂等性。

        try:  # 请求 GitHub 可能失败。
            github_data = self.github_client.get_repository(owner, repo)  # 获取 GitHub 仓库详情。
        except httpx.HTTPStatusError as exc:  # 捕获 GitHub 返回的 4xx/5xx。
            if exc.response.status_code == 404:  # 404 表示仓库不存在。
                raise ValueError(f"GitHub repository not found: {full_name}") from exc  # 转成业务错误，交给路由返回 400。
            raise  # 其他错误暂时继续抛出，后续再统一处理。

        repository = Repository(  # 把 GitHub 返回数据转换成 ORM 对象。
            owner=github_data["owner"]["login"],  # GitHub owner.login -> repositories.owner。
            name=github_data["name"],  # GitHub name -> repositories.name。
            full_name=github_data["full_name"],  # GitHub full_name -> repositories.full_name。
            html_url=github_data["html_url"],  # GitHub html_url -> repositories.html_url。
            homepage=github_data.get("homepage"),  # homepage 可能为空，用 get 更安全。
            description=github_data.get("description"),  # description 可能为空。
            primary_language=github_data.get("language"),  # language 可能为空。
            topics=github_data.get("topics") or [],  # topics 为空时保存空列表。
            license_name=(github_data.get("license") or {}).get("name"),  # license 可能是 None，所以先 or {}。
            stars=github_data.get("stargazers_count") or 0,  # stars 为空时保存 0。
            forks=github_data.get("forks_count") or 0,  # forks 为空时保存 0。
            watchers=github_data.get("watchers_count") or 0,  # watchers 为空时保存 0。
            open_issues=github_data.get("open_issues_count") or 0,  # open issues 为空时保存 0。
            archived=github_data.get("archived") or False,  # archived 为空时保存 False。
            disabled=github_data.get("disabled") or False,  # disabled 为空时保存 False。
            enabled=enabled,  # 使用请求体里的 enabled。
            source=source,  # 使用请求体里的 source。
            tags=tags or [],  # tags 不传时保存空列表。
            github_created_at=parse_github_datetime(github_data.get("created_at")),  # 转换 GitHub 创建时间。
            github_updated_at=parse_github_datetime(github_data.get("updated_at")),  # 转换 GitHub 更新时间。
            last_pushed_at=parse_github_datetime(github_data.get("pushed_at")),  # 转换最近 push 时间。
            last_collected_at=datetime.now(UTC),  # 记录本系统本次采集时间。
        )

        self.db.add(repository)  # 把 ORM 对象加入 Session。
        self.db.commit()  # 提交事务，真正写入 MySQL。
        self.db.refresh(repository)  # 刷新对象，拿到数据库最终状态。
        return repository  # 返回创建后的仓库对象。

    def list_repositories(self) -> list[Repository]:  # 查询仓库列表。
        statement = select(Repository).order_by(Repository.created_at.desc())  # 按创建时间倒序。
        return list(self.db.scalars(statement).all())  # 返回 ORM 对象列表。

    def get_repository(self, repository_id: str) -> Repository | None:  # 根据 id 查仓库。
        return self.db.get(Repository, repository_id)  # 主键查询，查不到返回 None。

    def get_by_full_name(self, full_name: str) -> Repository | None:  # 根据 owner/repo 查仓库。
        statement = select(Repository).where(Repository.full_name == full_name)  # 构造 full_name 查询条件。
        return self.db.scalar(statement)  # 查到返回对象，查不到返回 None。

    def update_repository(self, repository_id: str, enabled: bool | None = None, tags: list[str] | None = None) -> Repository | None:  # 更新仓库配置。
        repository = self.get_repository(repository_id)  # 先查仓库是否存在。
        if not repository:  # 如果仓库不存在。
            return None  # 交给路由层返回 404。

        if enabled is not None:  # enabled 不为 None 才更新。
            repository.enabled = enabled  # 修改启停状态。

        if tags is not None:  # tags 不为 None 才更新。
            repository.tags = tags  # 修改本地标签。

        self.db.commit()  # 提交修改。
        self.db.refresh(repository)  # 刷新对象。
        return repository  # 返回更新后的仓库。

    def _parse_full_name(self, full_name: str) -> tuple[str, str]:  # 校验并拆分 owner/repo。
        parts = full_name.strip().split("/")  # 去掉两端空格后按 / 拆分。
        if len(parts) != 2 or not parts[0] or not parts[1]:  # 必须正好两段且都非空。
            raise ValueError("full_name must be in owner/repo format")  # 格式错误时抛业务异常。
        return parts[0], parts[1]  # 返回 owner 和 repo。