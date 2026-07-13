from sqlalchemy import select  # 查询快照和任务记录。
from sqlalchemy.orm import Session  # 类型标注测试数据库会话。

from app.db.models import Job, StarSnapshot  # 用来断言 star_snapshots 和 jobs 写入结果。
from app.services.github_client import GitHubClient  # 测试中替换 GitHub 请求。
from tests.conftest import build_github_repository_data  # 构造固定 GitHub 响应。


def test_run_star_snapshot_creates_snapshot_and_job(client, db_session: Session, repository_factory, monkeypatch):
    """星标快照接口应采集仓库指标，写入快照，并留下 jobs 任务记录。"""
    repository = repository_factory(full_name="openai/openai-python", stars=100)

    def fake_get_repository(self: GitHubClient, owner: str, repo: str) -> dict:
        assert owner == "openai"
        assert repo == "openai-python"
        return build_github_repository_data("openai/openai-python", stars=150, forks=20, watchers=150, open_issues=8)

    monkeypatch.setattr(GitHubClient, "get_repository", fake_get_repository)

    response = client.post(
        "/api/v1/star-snapshots/runs",
        json={"repository_ids": [repository.id], "include_disabled": False},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "succeeded"
    assert body["total"] == 1
    assert body["succeeded"] == 1
    assert body["failed"] == 0
    assert body["snapshots"][0]["stars"] == 150

    snapshot = db_session.scalar(select(StarSnapshot).where(StarSnapshot.repository_id == repository.id))
    assert snapshot is not None
    assert snapshot.stars == 150

    job = db_session.get(Job, body["job_id"])
    assert job is not None
    assert job.job_type == "star_snapshot"
    assert job.status == "succeeded"
    assert job.progress == {"total": 1, "succeeded": 1, "failed": 0}
