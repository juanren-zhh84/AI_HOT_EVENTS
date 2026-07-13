from sqlalchemy import select  # 查询热点结果。
from sqlalchemy.orm import Session  # 类型标注测试数据库会话。

from app.db.models import HotProject  # 用来断言 hot_projects 写入结果。


def test_calculate_hot_projects_creates_ranked_result(
    client,
    db_session: Session,
    repository_factory,
    snapshot_factory,
    fixed_report_date,
    snapshot_times,
):
    """热点计算接口应基于快照生成热点榜单。"""
    previous_time, latest_time = snapshot_times
    repository = repository_factory(full_name="openai/openai-python", stars=150)
    snapshot_factory(repository, stars=100, snapshot_at=previous_time)
    snapshot_factory(repository, stars=150, snapshot_at=latest_time)

    response = client.post(
        "/api/v1/hot-projects/runs",
        json={"report_date": fixed_report_date.isoformat(), "top_n": 5, "include_disabled": False},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "succeeded"
    assert body["report_date"] == fixed_report_date.isoformat()
    assert body["total_candidates"] == 1
    assert body["generated"] == 1
    assert body["hot_projects"][0]["full_name"] == "openai/openai-python"
    assert body["hot_projects"][0]["stars_delta_24h"] == 50

    hot_project = db_session.scalar(select(HotProject).where(HotProject.report_date == fixed_report_date))
    assert hot_project is not None
    assert hot_project.rank_no == 1
    assert hot_project.stars_delta_24h == 50
