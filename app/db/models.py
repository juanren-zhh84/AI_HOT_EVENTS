# app/db/models.py
"""
数据库 ORM 模型。

ORM 可以理解为“数据库表的 Python 版本”：
1. 数据库里的 repositories 表，对应这里的 Repository 类。
2. 数据库里的 star_snapshots 表，对应这里的 StarSnapshot 类。
3. 数据库里的 jobs 表，对应这里的 Job 类。

为什么要写 ORM 模型？
以后业务代码可以用 Python 对象操作数据库，不需要到处手写 SQL。
例如创建仓库时，可以写 Repository(...)，再 db.add(repository)。
"""

import uuid  # 用来生成 UUID 字符串，作为每条数据的主键 id。
from datetime import date, datetime  # date 用来声明 report_date；datetime 用来声明日期时间字段。

from sqlalchemy import (  # SQLAlchemy 提供数据库字段类型、外键、约束和 SQL 函数。
    Boolean,  # 用来映射 MySQL 的 TINYINT(1)。
    Date,  # 用来映射 MySQL 的 DATE 字段，例如 hot_projects.report_date。
    DateTime,  # 用来映射 MySQL 的 DATETIME 字段。
    ForeignKey,  # 用来声明外键关系。
    Integer,  # 用来映射 MySQL 的 INT 字段。
    JSON,  # 用来映射 MySQL 的 JSON 字段。
    Numeric,  # 用来映射 MySQL 的 DECIMAL 字段，例如 hot_score、growth_rate_24h。
    String,  # 用来映射 MySQL 的 VARCHAR/CHAR 字段。
    Text,  # 用来映射 MySQL 的 TEXT 字段。
    UniqueConstraint,  # 用来声明联合唯一约束。
    func, Nullable,  # 用来调用数据库函数。
)
from sqlalchemy.ext.mutable import MutableDict, MutableList  # 让 JSON 字典/列表的内部修改能被 ORM 识别。
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship  # SQLAlchemy 2.x 推荐的 ORM 声明方式。


def uuid_str() -> str:  # 定义一个生成 UUID 字符串的函数，给主键默认值使用。
    """
    生成一个 UUID 字符串。

    为什么不完全依赖 MySQL 的 DEFAULT (UUID())？
    1. Python 端先生成 id，创建对象后立刻就能拿到主键。
    2. 后面创建关联数据时，例如 StarSnapshot.repository_id，会更方便。
    3. 不依赖具体 MySQL 版本是否支持表达式默认值。
    """
    return str(uuid.uuid4())  # uuid.uuid4() 生成随机 UUID，str(...) 把它转成数据库 CHAR(36) 能保存的字符串。


class Base(DeclarativeBase):  # 所有 ORM 模型都继承这个 Base，SQLAlchemy 才知道这些类是表模型。
    """
    ORM 基类。

    Repository、StarSnapshot、Job 都继承 Base。
    继承后，SQLAlchemy 会把这些类纳入 ORM 管理。
    """
    pass  # Base 本身不需要字段，只作为所有模型的公共父类。


class Repository(Base):  # Repository 类对应 repositories 表。
    """
    repositories 表的 ORM 模型。

    这张表保存 GitHub 仓库的基础信息：
    仓库名、描述、链接、语言、stars、forks、issues、是否启用监控等。
    """

    __tablename__ = "repositories"  # 告诉 SQLAlchemy：这个类对应数据库里的 repositories 表。

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)  # 主键，使用 UUID 字符串，避免不同数据之间 id 冲突。

    owner: Mapped[str] = mapped_column(String(255), nullable=False)  # GitHub 仓库拥有者，例如 openai/openai-python 里的 openai。

    name: Mapped[str] = mapped_column(String(255), nullable=False)  # GitHub 仓库名称，例如 openai/openai-python 里的 openai-python。

    full_name: Mapped[str] = mapped_column(String(511), nullable=False, unique=True)  # 仓库完整名 owner/repo，unique=True 防止重复添加同一个仓库。

    html_url: Mapped[str] = mapped_column(Text, nullable=False)  # GitHub 仓库网页地址，不能为空，因为后续邮件和列表需要跳转链接。

    homepage: Mapped[str | None] = mapped_column(Text)  # 项目主页地址，有些仓库没有主页，所以允许为 None。

    description: Mapped[str | None] = mapped_column(Text)  # 仓库描述，有些仓库没有 description，所以允许为 None。

    primary_language: Mapped[str | None] = mapped_column(String(100))  # GitHub 识别出的主语言，例如 Python、TypeScript；有些仓库可能没有语言。

    topics: Mapped[list[str]] = mapped_column(  # topics 是 GitHub 仓库标签列表，例如 ["ai", "python"]。
        MutableList.as_mutable(JSON),  # JSON 列表需要 MutableList，否则 repo.topics.append(...) 这种内部变化可能不会被 ORM 检测到。
        nullable=False,  # 数据库中不允许为空，保证业务代码总能拿到列表。
        default=list,  # 默认给空列表，避免使用 None 后还要额外判断。
    )

    license_name: Mapped[str | None] = mapped_column(String(255))  # 许可证名称，例如 MIT、Apache-2.0；仓库可能没有许可证。

    stars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 当前总 star 数，默认 0，便于排序和热点计算。

    forks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 当前 fork 数，默认 0，作为项目活跃度参考。

    watchers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 当前 watchers 数，默认 0，和 GitHub 返回字段保持对应。

    open_issues: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 当前 open issue 数，默认 0，后续可用于活跃度评分。

    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # 是否归档；归档项目通常不适合进入热点推荐。

    disabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # 是否被 GitHub 禁用；禁用项目后续采集应跳过。

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)  # 本系统是否启用监控；用户可以暂停某个仓库。

    source: Mapped[str] = mapped_column(String(100), nullable=False, default="manual")  # 仓库来源，例如 manual、github_search、topic。

    tags: Mapped[list[str]] = mapped_column(  # 本系统自己的标签，不等同于 GitHub topics。
        MutableList.as_mutable(JSON),  # JSON 列表使用 MutableList，确保修改列表内容时 ORM 能识别变化。
        nullable=False,  # 不允许为空，避免业务代码处理 None。
        default=list,  # 默认空列表，表示还没有人为打标签。
    )

    github_created_at: Mapped[datetime | None] = mapped_column(DateTime)  # 仓库在 GitHub 上的创建时间，来自 GitHub API 的 created_at。

    github_updated_at: Mapped[datetime | None] = mapped_column(DateTime)  # 仓库在 GitHub 上的更新时间，来自 GitHub API 的 updated_at。

    last_pushed_at: Mapped[datetime | None] = mapped_column(DateTime)  # 仓库最近一次 push 时间，后续可判断项目是否仍活跃。

    last_collected_at: Mapped[datetime | None] = mapped_column(DateTime)  # 本系统最近一次成功采集该仓库信息的时间。

    created_at: Mapped[datetime] = mapped_column(  # 本系统创建这条仓库记录的时间。
        DateTime,  # 使用 DATETIME 类型保存时间。
        nullable=False,  # 创建时间必须存在。
        server_default=func.now(),  # 如果 Python 没传值，就由数据库自动填当前时间。
    )

    updated_at: Mapped[datetime] = mapped_column(  # 本系统最后更新这条仓库记录的时间。
        DateTime,  # 使用 DATETIME 类型保存时间。
        nullable=False,  # 更新时间必须存在。
        server_default=func.now(),  # 插入时由数据库自动填当前时间。
        onupdate=func.now(),  # ORM 更新记录时自动刷新为当前时间。
    )

    snapshots: Mapped[list["StarSnapshot"]] = relationship(  # 一个仓库可以有多条星标快照。
        back_populates="repository",  # 和 StarSnapshot.repository 配对，形成双向关系。
        cascade="all, delete-orphan",  # 删除仓库对象时，ORM 层也会删除它关联的快照对象。
    )

    hot_projects: Mapped[list["HotProject"]] = relationship(# 一个仓库可以出现在多天热点榜里，所以是一对多关系。
        back_populates="repository",# 和 HotProject.repository 配对，方便双向访问。
        cascade="all, delete-orphan",# 删除仓库时，ORM 层同步删除关联热点记录。
    )


class StarSnapshot(Base):  # StarSnapshot 类对应 star_snapshots 表。
    """
    star_snapshots 表的 ORM 模型。

    这张表保存仓库在某个时间点的指标快照。
    例如某仓库在 2026-06-23 10:00 有 25000 stars。
    后续 24 小时增长、7 天增长，都依赖这张表计算。
    """

    __tablename__ = "star_snapshots"  # 告诉 SQLAlchemy：这个类对应数据库里的 star_snapshots 表。

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)  # 快照主键，使用 UUID 字符串。

    repository_id: Mapped[str] = mapped_column(  # 外键字段，表示这条快照属于哪个仓库。
        String(36),  # 类型和 repositories.id 保持一致。
        ForeignKey("repositories.id", ondelete="CASCADE", onupdate="CASCADE"),  # 外键指向 repositories.id，仓库删除或更新 id 时同步处理。
        nullable=False,  # 快照必须属于某个仓库，不能没有 repository_id。
    )

    stars: Mapped[int] = mapped_column(Integer, nullable=False)  # 快照时刻的 star 数，不能为空，因为热点计算必须依赖它。

    forks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 快照时刻的 fork 数，默认 0。

    watchers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 快照时刻的 watcher 数，默认 0。

    open_issues: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 快照时刻的 open issue 数，默认 0。

    source: Mapped[str] = mapped_column(String(100), nullable=False, default="github_rest")  # 快照数据来源，默认来自 GitHub REST API。

    snapshot_at: Mapped[datetime] = mapped_column(  # 这条快照对应的采集时间点。
        DateTime,  # 使用 DATETIME 保存时间点。
        nullable=False,  # 快照时间必须存在，否则无法计算时间窗口增长。
        server_default=func.now(),  # 如果 Python 没传采集时间，就由数据库填当前时间。
    )

    created_at: Mapped[datetime] = mapped_column(  # 本系统创建这条快照记录的时间。
        DateTime,  # 使用 DATETIME 类型。
        nullable=False,  # 创建时间必须存在。
        server_default=func.now(),  # 插入时由数据库自动填当前时间。
    )

    repository: Mapped[Repository] = relationship(back_populates="snapshots")  # 反向关联到 Repository，方便通过 snapshot.repository 访问所属仓库。

    __table_args__ = (  # 表级配置，用来声明联合唯一约束。
        UniqueConstraint(  # 同一个仓库在同一个快照时间只能有一条记录，避免重复采集插入重复数据。
            "repository_id",  # 联合唯一约束的第一个字段：仓库 id。
            "snapshot_at",  # 联合唯一约束的第二个字段：快照时间。
            name="uq_star_snapshots_repo_time",  # 约束名称，和建表 SQL 保持一致，方便排查数据库错误。
        ),
    )

class HotProject(Base):
    """
    hot_projects表的ORM模型
    保存每天计算出来的热电项目榜单（计算结果来自star_snapshots）
    """
    __tablename__ = "hot_projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    repository_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("repositories.id", ondelete="CASCADE", onupdate="CASCADE"),# 仓库删除时，热点记录也一起删除。
        nullable=False,
    )
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    rank_no: Mapped[int] = mapped_column(Integer, nullable=False)  # 排名，从 1 开始。
    hot_score: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False, default=0)  # 热度分，用来排序。
    stars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 计算时的总 star 数。
    stars_delta_24h: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 近 24 小时新增 star 数。
    stars_delta_7d: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 近 7 天新增 star 数。
    growth_rate_24h: Mapped[float] = mapped_column(Numeric(12, 6), nullable=False, default=0)  # 24 小时增长率。
    reason: Mapped[str | None] = mapped_column(Text)  # 入选原因，方便邮件日报展示。
    created_at: Mapped[datetime] = mapped_column(  # 本系统创建这条热点记录的时间。
        DateTime,  # 使用 DATETIME 类型。
        nullable=False,  # 创建时间必须存在。
        server_default=func.now(),  # 插入时由数据库自动填当前时间。
    )

    updated_at: Mapped[datetime] = mapped_column(  # 本系统最后更新这条热点记录的时间。
        DateTime,  # 使用 DATETIME 类型。
        nullable=False,  # 更新时间必须存在。
        server_default=func.now(),  # 插入时由数据库自动填当前时间。
        onupdate=func.now(),  # ORM 更新记录时自动刷新更新时间。
    )

    repository: Mapped[Repository] = relationship(back_populates="hot_projects") # 反向关联到 Repository。

    __table_args__ = (  # 表级配置，用来声明联合唯一约束。
        UniqueConstraint("report_date", "repository_id", name="uq_hot_projects_report_repo"),  # 同一天同一仓库只能有一条热点记录。
        UniqueConstraint("report_date", "rank_no", name="uq_hot_projects_report_rank"),  # 同一天同一个排名只能有一条记录。
    )
    

class Subscriber(Base):  # Subscriber 类对应 subscribers 表。
    """
    subscribers 表的 ORM 模型。

    这张表保存邮件订阅者。
    只有 status='active' 的订阅者，才会收到日报。
    """

    __tablename__ = "subscribers"  # 告诉 SQLAlchemy：这个类对应 subscribers 表。

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)  # 订阅者主键，使用 UUID 字符串。

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)  # 订阅者邮箱，unique=True 避免重复订阅。

    name: Mapped[str | None] = mapped_column(String(255))  # 订阅者名称，可以为空。

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")  # 订阅状态：active、paused、unsubscribed。

    preferences: Mapped[dict] = mapped_column(  # 订阅偏好，后续可保存语言、主题、数量等配置。
        MutableDict.as_mutable(JSON),  # JSON 字典使用 MutableDict，方便 ORM 识别内部修改。
        nullable=False,  # 不允许为空，保证业务代码总能拿到 dict。
        default=dict,  # 默认空字典，表示暂无偏好。
    )

    unsubscribe_token: Mapped[str] = mapped_column(String(36), nullable=False, default=uuid_str, unique=True)  # 退订 token，后续做退订链接用。

    unsubscribed_at: Mapped[datetime | None] = mapped_column(DateTime)  # 退订时间，未退订时为空。

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())  # 创建时间。

    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())  # 更新时间。


class EmailReport(Base):  # EmailReport 类对应 email_reports 表。
    """
    email_reports 表的 ORM 模型。

    这张表保存每天生成出来的日报内容。
    一天只生成一份报告，发送给多个订阅者。
    """

    __tablename__ = "email_reports"  # 告诉 SQLAlchemy：这个类对应 email_reports 表。

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)  # 邮件日报主键。

    report_date: Mapped[date] = mapped_column(Date, nullable=False, unique=True)  # 日报日期，一天只允许一份报告。

    subject: Mapped[str] = mapped_column(String(255), nullable=False)  # 邮件标题。

    html_content: Mapped[str] = mapped_column(Text, nullable=False)  # HTML 邮件内容。

    text_content: Mapped[str] = mapped_column(Text, nullable=False)  # 纯文本邮件内容。

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")  # 报告状态：draft、sending、sent、failed。

    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())  # 生成时间。

    sent_at: Mapped[datetime | None] = mapped_column(DateTime)  # 发送完成时间。

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())  # 创建时间。

    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())  # 更新时间。

    deliveries: Mapped[list["EmailDelivery"]] = relationship(  # 一份日报会发给多个订阅者，所以有多条投递记录。
        back_populates="report",  # 和 EmailDelivery.report 配对。
        cascade="all, delete-orphan",  # 删除日报时，同步删除对应投递记录。
    )


class EmailDelivery(Base):  # EmailDelivery 类对应 email_deliveries 表。
    """
    email_deliveries 表的 ORM 模型。

    这张表保存每个订阅者的发送结果。
    同一份日报发给 10 个人，就会有 10 条投递记录。
    """

    __tablename__ = "email_deliveries"  # 告诉 SQLAlchemy：这个类对应 email_deliveries 表。

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)  # 投递记录主键。

    report_id: Mapped[str] = mapped_column(String(36), ForeignKey("email_reports.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False)  # 关联 email_reports.id。

    subscriber_id: Mapped[str] = mapped_column(String(36), ForeignKey("subscribers.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False)  # 关联 subscribers.id。

    email: Mapped[str] = mapped_column(String(320), nullable=False)  # 实际发送邮箱，冗余保存方便排查。

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # 发送状态：pending、sending、sent、failed、skipped。

    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 重试次数，本阶段先不做自动重试。

    error_message: Mapped[str | None] = mapped_column(Text)  # 失败原因，成功时为空。

    sent_at: Mapped[datetime | None] = mapped_column(DateTime)  # 发送成功时间。

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())  # 创建时间。

    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())  # 更新时间。

    report: Mapped[EmailReport] = relationship(back_populates="deliveries")  # 反向关联到 EmailReport。

    subscriber: Mapped[Subscriber] = relationship()  # 反向关联到 Subscriber，方便通过 delivery.subscriber 访问订阅者。

    __table_args__ = (  # 表级配置。
        UniqueConstraint("report_id", "subscriber_id", name="uq_email_deliveries_report_subscriber"),  # 同一份日报给同一订阅者只能有一条投递记录。
    )


class Job(Base):  # Job 类对应 jobs 表。
    """
    jobs 表的 ORM 模型。

    这张表记录后台任务或手动触发任务。
    例如仓库采集任务、星标快照任务、热点计算任务、邮件发送任务。
    """

    __tablename__ = "jobs"  # 告诉 SQLAlchemy：这个类对应数据库里的 jobs 表。

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)  # 任务主键，使用 UUID 字符串。

    job_type: Mapped[str] = mapped_column("type", String(50), nullable=False)  # Python 属性叫 job_type，但数据库字段叫 type，避免和 Python 内置 type 混淆。

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # 任务状态，例如 pending、running、succeeded、failed、cancelled。

    payload: Mapped[dict] = mapped_column(  # 任务参数，例如要采集哪些仓库。
        MutableDict.as_mutable(JSON),  # JSON 字典使用 MutableDict，确保修改内部 key/value 时 ORM 能识别变化。
        nullable=False,  # 不允许为空，保证业务代码总能拿到字典。
        default=dict,  # 默认空字典，表示没有额外参数。
    )

    progress: Mapped[dict] = mapped_column(  # 任务进度，例如 total、succeeded、failed。
        MutableDict.as_mutable(JSON),  # JSON 字典使用 MutableDict，方便原地更新进度字段。
        nullable=False,  # 不允许为空，保证任务查询时总能返回进度结构。
        default=dict,  # 默认空字典，表示任务还没有进度数据。
    )

    error_message: Mapped[str | None] = mapped_column(Text)  # 任务失败原因，成功或未失败时可以为空。

    started_at: Mapped[datetime | None] = mapped_column(DateTime)  # 任务开始时间，任务还没开始时为空。

    finished_at: Mapped[datetime | None] = mapped_column(DateTime)  # 任务结束时间，任务未结束时为空。

    created_at: Mapped[datetime] = mapped_column(  # 本系统创建这条任务记录的时间。
        DateTime,  # 使用 DATETIME 类型。
        nullable=False,  # 创建时间必须存在。
        server_default=func.now(),  # 插入时由数据库自动填当前时间。
    )

    updated_at: Mapped[datetime] = mapped_column(  # 本系统最后更新这条任务记录的时间。
        DateTime,  # 使用 DATETIME 类型。
        nullable=False,  # 更新时间必须存在。
        server_default=func.now(),  # 插入时由数据库自动填当前时间。
        onupdate=func.now(),  # ORM 更新任务状态或进度时自动刷新更新时间。
    )
