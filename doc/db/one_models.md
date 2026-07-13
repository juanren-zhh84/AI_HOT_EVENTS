```python
# app/db/models.py

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def uuid_str() -> str:
    """
    生成一个 UUID 字符串。

    为什么要自己生成？
    你的 MySQL 表里虽然写了 DEFAULT (UUID())，
    但如果让数据库生成 id，Python 代码有时候不能立刻拿到这个 id。

    ORM 里自己生成 id 的好处是：
    1. 插入数据库前，Python 对象就已经有 id。
    2. 后面创建关联数据，比如 star_snapshots，需要 repository_id，会更方便。
    3. 不依赖某个 MySQL 版本对 UUID() 默认值的支持。
    """
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    """
    所有 ORM 模型的基类。

    你可以理解为：
    Repository、StarSnapshot、Job 都要继承 Base，
    SQLAlchemy 才知道它们是数据库表模型。

    DeclarativeBase 是 SQLAlchemy 2.x 推荐的新写法。
    """
    pass


class Repository(Base):
    """
    repositories 表的 ORM 模型。

    这张表用来保存 GitHub 仓库的基础信息，
    例如 openai/openai-python 的名称、描述、stars、forks 等。
    """

    # 这个类对应数据库里的 repositories 表
    __tablename__ = "repositories"

    # 主键 id，对应 CHAR(36)
    # default=uuid_str 表示创建 Repository 对象时自动生成 UUID
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)

    # GitHub 仓库 owner，比如 openai/openai-python 里的 openai
    owner: Mapped[str] = mapped_column(String(255), nullable=False)

    # GitHub 仓库名，比如 openai/openai-python 里的 openai-python
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # 仓库完整名，比如 openai/openai-python
    # unique=True 表示数据库里不能重复监控同一个仓库
    full_name: Mapped[str] = mapped_column(String(511), nullable=False, unique=True)

    # GitHub 页面地址，比如 https://github.com/openai/openai-python
    html_url: Mapped[str] = mapped_column(Text, nullable=False)

    # 项目主页，有些仓库没有，所以允许为空
    homepage: Mapped[str | None] = mapped_column(Text)

    # 仓库描述，有些仓库也可能没有，所以允许为空
    description: Mapped[str | None] = mapped_column(Text)

    # 主语言，比如 Python、TypeScript、Go
    primary_language: Mapped[str | None] = mapped_column(String(100))

    # topics 是 JSON 数组，比如 ["ai", "python", "sdk"]
    #
    # 为什么用 MutableList.as_mutable(JSON)？
    # 普通 JSON 字段如果你这样改：
    # repo.topics.append("ai")
    # SQLAlchemy 可能不知道它变了。
    #
    # MutableList 可以让 SQLAlchemy 感知列表内部变化。
    topics: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON),
        nullable=False,
        default=list,
    )

    # 许可证名称，比如 MIT、Apache-2.0
    license_name: Mapped[str | None] = mapped_column(String(255))

    # 当前 stars 数
    stars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # 当前 forks 数
    forks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # 当前 watchers 数
    watchers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # 当前 open issues 数
    open_issues: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # 是否归档
    # MySQL 里是 TINYINT(1)，ORM 里可以写成 Boolean
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # 是否不可用
    disabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # 是否启用监控
    # 以后如果你暂停某个仓库，就把 enabled 改成 False
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # 仓库来源，比如 manual、github_search、topic
    source: Mapped[str] = mapped_column(String(100), nullable=False, default="manual")

    # 本地标签，比如 ["ai", "sdk"]
    tags: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON),
        nullable=False,
        default=list,
    )

    # GitHub 上的创建时间
    github_created_at: Mapped[datetime | None] = mapped_column(DateTime)

    # GitHub 上的更新时间
    github_updated_at: Mapped[datetime | None] = mapped_column(DateTime)

    # 最近 push 时间
    last_pushed_at: Mapped[datetime | None] = mapped_column(DateTime)

    # 本系统最近一次采集时间
    last_collected_at: Mapped[datetime | None] = mapped_column(DateTime)

    # 本系统创建这条记录的时间
    #
    # server_default=func.now() 表示：
    # 如果 Python 没传 created_at，就让数据库自动填当前时间。
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    # 本系统更新这条记录的时间
    #
    # onupdate=func.now() 表示：
    # ORM 更新这条记录时，自动刷新 updated_at。
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # relationship 表示“对象之间的关系”
    #
    # 一个 Repository 可以有多条 StarSnapshot。
    #
    # 以后你可以这样访问：
    # repo.snapshots
    #
    # back_populates 要和 StarSnapshot 里的 repository 对应。
    snapshots: Mapped[list["StarSnapshot"]] = relationship(
        back_populates="repository",
        cascade="all, delete-orphan",
    )


class StarSnapshot(Base):
    """
    star_snapshots 表的 ORM 模型。

    这张表用来保存某个仓库在某个时间点的 stars 快照。
    比如：
    2026-06-02 10:00，openai/openai-python 有 25000 stars。
    """

    __tablename__ = "star_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)

    # repository_id 是外键，指向 repositories.id
    #
    # ForeignKey 的作用：
    # 保证这条快照一定属于某个存在的仓库。
    #
    # ondelete="CASCADE" 表示：
    # 如果某个仓库被删除，它的快照也一起删除。
    repository_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("repositories.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )

    stars: Mapped[int] = mapped_column(Integer, nullable=False)
    forks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    watchers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    open_issues: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # 数据来源，默认来自 GitHub REST API
    source: Mapped[str] = mapped_column(String(100), nullable=False, default="github_rest")

    # 快照时间
    # 如果 Python 没传，就让数据库填当前时间
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    # 反向关系：这条快照属于哪个仓库
    #
    # 以后你可以这样访问：
    # snapshot.repository
    repository: Mapped[Repository] = relationship(back_populates="snapshots")

    # 复合唯一约束
    #
    # 表示同一个仓库在同一个 snapshot_at 时间点只能有一条快照。
    # 这样可以避免重复采集时插入重复数据。
    __table_args__ = (
        UniqueConstraint(
            "repository_id",
            "snapshot_at",
            name="uq_star_snapshots_repo_time",
        ),
    )


class Job(Base):
    """
    jobs 表的 ORM 模型。

    这张表用来记录异步任务或手动触发任务。
    比如：
    - GitHub 仓库采集任务
    - 星标快照任务
    - 热点项目计算任务
    - 邮件发送任务
    """

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)

    # 数据库字段名叫 type。
    #
    # 但是 Python 里 type 是内置函数名。
    # 为了避免混淆，Python 属性名用 job_type，
    # 但 mapped_column("type") 表示它实际对应数据库里的 type 字段。
    job_type: Mapped[str] = mapped_column("type", String(50), nullable=False)

    # 任务状态：
    # pending    等待执行
    # running    执行中
    # succeeded  执行成功
    # failed     执行失败
    # cancelled  已取消
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")

    # 任务参数
    #
    # 比如手动触发星标快照时，可以保存：
    # {
    #   "repository_ids": ["xxx"],
    #   "force": false
    # }
    payload: Mapped[dict] = mapped_column(
        MutableDict.as_mutable(JSON),
        nullable=False,
        default=dict,
    )

    # 任务进度
    #
    # 比如：
    # {
    #   "total": 100,
    #   "succeeded": 95,
    #   "failed": 5
    # }
    progress: Mapped[dict] = mapped_column(
        MutableDict.as_mutable(JSON),
        nullable=False,
        default=dict,
    )

    # 错误信息
    # 任务失败时可以记录异常原因
    error_message: Mapped[str | None] = mapped_column(Text)

    # 任务开始时间
    started_at: Mapped[datetime | None] = mapped_column(DateTime)

    # 任务结束时间
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
```

