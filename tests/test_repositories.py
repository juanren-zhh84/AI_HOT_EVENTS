from sqlalchemy import select  # 查询数据库，确认接口真的写入了 repositories 表。
from sqlalchemy.orm import Session  # 类型标注测试数据库会话。

from app.db.models import Repository  # 仓库 ORM 模型，用来做数据库断言。
from app.services.github_client import GitHubClient  # 测试中替换 GitHub 请求，避免访问真实网络。
from tests.conftest import build_github_repository_data  # 复用固定 GitHub 响应构造函数。


def test_create_repository_writes_repository(client, db_session: Session, monkeypatch):
    """创建仓库接口应写入数据库，并返回 GitHub 仓库基础信息。"""
    def fake_get_repository(self: GitHubClient, owner: str, repo: str) -> dict:
        # 断言接口把 full_name 正确拆成 owner/repo 后才调用 GitHubClient。
        assert owner == "openai"
        assert repo == "openai-python"
        return build_github_repository_data("openai/openai-python", stars=123)

    monkeypatch.setattr(GitHubClient, "get_repository", fake_get_repository)

    response = client.post(
        "/api/v1/repositories",
        json={"full_name": "openai/openai-python", "source": "manual", "tags": ["sdk"], "enabled": True},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["full_name"] == "openai/openai-python"
    assert body["stars"] == 123
    assert body["tags"] == ["sdk"]

    repository = db_session.scalar(select(Repository).where(Repository.full_name == "openai/openai-python"))
    assert repository is not None
    assert repository.enabled is True
