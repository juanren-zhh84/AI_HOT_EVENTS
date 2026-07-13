import os  # 读取 TEST_DATABASE_URL，确保测试只连接专门的测试库。
from collections.abc import Generator  # 给 pytest fixture 的 yield 返回值做类型标注。
from datetime import UTC, date, datetime, timedelta  # 构造测试数据里的日期和时间。

import pytest  # 提供 fixture、测试退出等能力。
from fastapi.testclient import TestClient  # 用真实 HTTP 方式调用 FastAPI 路由。
from sqlalchemy import create_engine  # 为测试库创建独立 SQLAlchemy engine。
from sqlalchemy.engine import make_url  # 解析数据库 URL，检查是不是安全的测试库。
from sqlalchemy.orm import Session, sessionmaker  # 创建测试 Session。

from app.core.config import settings  # 测试中关闭调度器，避免启动 TestClient 时自动跑任务。
from app.db.models import Base, HotProject, Repository, StarSnapshot, Subscriber, uuid_str  # 复用正式 ORM 模型建表和造数据。
from app.db.session import get_db  # 被路由 Depends 使用的数据库依赖，测试里要覆盖它。
from app.main import app  # 导入真实 FastAPI 应用，保证测试走真实路由。


def _load_test_database_url() -> str:
    """读取并校验测试数据库 URL，避免测试误删正式数据库。"""
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.exit("请先设置 TEST_DATABASE_URL，并指向名称以 _test 结尾的 MySQL 测试库。")

    url = make_url(database_url)
    if not url.drivername.startswith("mysql"):
        pytest.exit("TEST_DATABASE_URL 必须使用 MySQL，例如 mysql+pymysql://.../aihotevent_test。")
    if not url.database or not url.database.endswith("_test"):
        pytest.exit("TEST_DATABASE_URL 的数据库名必须以 _test 结尾，防止误删正式库。")
    return database_url


TEST_DATABASE_URL = _load_test_database_url()

test_engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    """每个测试使用一套空表，保证测试之间互不影响。"""
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture()
def client(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    """创建测试客户端，并把 FastAPI 的数据库依赖替换成测试 Session。"""
    monkeypatch.setattr(settings, "scheduler_enabled", False)

    def override_get_db() -> Generator[Session, None, None]:
        # 这里复用同一个测试 Session，方便接口调用后继续在测试里查询数据库断言。
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides = {}


def build_github_repository_data(
    full_name: str = "openai/openai-python",
    stars: int = 100,
    forks: int = 10,
    watchers: int = 100,
    open_issues: int = 5,
) -> dict:
    """构造 GitHub API 的仓库详情响应，避免测试访问真实 GitHub。"""
    owner, name = full_name.split("/", maxsplit=1)
    return {
        "owner": {"login": owner},
        "name": name,
        "full_name": full_name,
        "html_url": f"https://github.com/{full_name}",
        "homepage": None,
        "description": f"{full_name} test repository",
        "language": "Python",
        "topics": ["ai", "test"],
        "license": {"name": "MIT"},
        "stargazers_count": stars,
        "forks_count": forks,
        "watchers_count": watchers,
        "open_issues_count": open_issues,
        "archived": False,
        "disabled": False,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-02T00:00:00Z",
        "pushed_at": "2026-01-03T00:00:00Z",
    }


@pytest.fixture()
def repository_factory(db_session: Session):
    """直接插入仓库数据，供快照、热点、邮件测试复用。"""
    def create_repository(
        full_name: str = "openai/openai-python",
        stars: int = 100,
        enabled: bool = True,
    ) -> Repository:
        owner, name = full_name.split("/", maxsplit=1)
        repository = Repository(
            id=uuid_str(),
            owner=owner,
            name=name,
            full_name=full_name,
            html_url=f"https://github.com/{full_name}",
            homepage=None,
            description=f"{full_name} test repository",
            primary_language="Python",
            topics=["ai", "test"],
            license_name="MIT",
            stars=stars,
            forks=10,
            watchers=stars,
            open_issues=5,
            archived=False,
            disabled=False,
            enabled=enabled,
            source="test",
            tags=["test"],
            github_created_at=datetime(2026, 1, 1, tzinfo=UTC),
            github_updated_at=datetime(2026, 1, 2, tzinfo=UTC),
            last_pushed_at=datetime(2026, 1, 3, tzinfo=UTC),
            last_collected_at=datetime(2026, 1, 4, tzinfo=UTC),
        )
        db_session.add(repository)
        db_session.commit()
        db_session.refresh(repository)
        return repository

    return create_repository


@pytest.fixture()
def snapshot_factory(db_session: Session):
    """直接插入星标快照，供热点计算测试复用。"""
    def create_snapshot(repository: Repository, stars: int, snapshot_at: datetime) -> StarSnapshot:
        snapshot = StarSnapshot(
            repository_id=repository.id,
            stars=stars,
            forks=repository.forks,
            watchers=stars,
            open_issues=repository.open_issues,
            source="test",
            snapshot_at=snapshot_at,
        )
        db_session.add(snapshot)
        db_session.commit()
        db_session.refresh(snapshot)
        return snapshot

    return create_snapshot


@pytest.fixture()
def hot_project_factory(db_session: Session, repository_factory):
    """直接插入热点项目，供邮件日报测试复用。"""
    def create_hot_project(report_date: date, repository: Repository | None = None) -> HotProject:
        current_repository = repository or repository_factory()
        hot_project = HotProject(
            repository_id=current_repository.id,
            report_date=report_date,
            rank_no=1,
            hot_score=88.88,
            stars=current_repository.stars,
            stars_delta_24h=12,
            stars_delta_7d=35,
            growth_rate_24h=0.12,
            reason="测试热点项目。",
        )
        db_session.add(hot_project)
        db_session.commit()
        db_session.refresh(hot_project)
        return hot_project

    return create_hot_project


@pytest.fixture()
def subscriber_factory(db_session: Session):
    """直接插入订阅者，供邮件发送测试复用。"""
    def create_subscriber(email: str = "tester@example.com") -> Subscriber:
        subscriber = Subscriber(email=email, name="测试订阅者", status="active", preferences={})
        db_session.add(subscriber)
        db_session.commit()
        db_session.refresh(subscriber)
        return subscriber

    return create_subscriber


@pytest.fixture()
def fixed_report_date() -> date:
    """固定日报日期，让测试不受当前日期影响。"""
    return date(2026, 1, 5)


@pytest.fixture()
def snapshot_times() -> tuple[datetime, datetime]:
    """提供一组相差超过 24 小时的快照时间，用来稳定计算热点增长。"""
    latest = datetime.now(UTC) - timedelta(hours=1)
    previous = latest - timedelta(hours=25)
    return previous, latest
