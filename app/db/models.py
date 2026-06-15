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
    鐢熸垚涓€涓?UUID 瀛楃涓层€?

    涓轰粈涔堣鑷繁鐢熸垚锛?
    浣犵殑 MySQL 琛ㄩ噷铏界劧鍐欎簡 DEFAULT (UUID())锛?
    浣嗗鏋滆鏁版嵁搴撶敓鎴?id锛孭ython 浠ｇ爜鏈夋椂鍊欎笉鑳界珛鍒绘嬁鍒拌繖涓?id銆?

    ORM 閲岃嚜宸辩敓鎴?id 鐨勫ソ澶勬槸锛?
    1. 鎻掑叆鏁版嵁搴撳墠锛孭ython 瀵硅薄灏卞凡缁忔湁 id銆?
    2. 鍚庨潰鍒涘缓鍏宠仈鏁版嵁锛屾瘮濡?star_snapshots锛岄渶瑕?repository_id锛屼細鏇存柟渚裤€?
    3. 涓嶄緷璧栨煇涓?MySQL 鐗堟湰瀵?UUID() 榛樿鍊肩殑鏀寔銆?
    """
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    """
    鎵€鏈?ORM 妯″瀷鐨勫熀绫汇€?

    浣犲彲浠ョ悊瑙ｄ负锛?
    Repository銆丼tarSnapshot銆丣ob 閮借缁ф壙 Base锛?
    SQLAlchemy 鎵嶇煡閬撳畠浠槸鏁版嵁搴撹〃妯″瀷銆?

    DeclarativeBase 鏄?SQLAlchemy 2.x 鎺ㄨ崘鐨勬柊鍐欐硶銆?
    """
    pass


class Repository(Base):
    """
    repositories 琛ㄧ殑 ORM 妯″瀷銆?

    杩欏紶琛ㄧ敤鏉ヤ繚瀛?GitHub 浠撳簱鐨勫熀纭€淇℃伅锛?
    渚嬪 openai/openai-python 鐨勫悕绉般€佹弿杩般€乻tars銆乫orks 绛夈€?
    """

    # 杩欎釜绫诲搴旀暟鎹簱閲岀殑 repositories 琛?
    __tablename__ = "repositories"

    # 涓婚敭 id锛屽搴?CHAR(36)
    # default=uuid_str 琛ㄧず鍒涘缓 Repository 瀵硅薄鏃惰嚜鍔ㄧ敓鎴?UUID
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)

    # GitHub 浠撳簱 owner锛屾瘮濡?openai/openai-python 閲岀殑 openai
    owner: Mapped[str] = mapped_column(String(255), nullable=False)

    # GitHub 浠撳簱鍚嶏紝姣斿 openai/openai-python 閲岀殑 openai-python
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # 浠撳簱瀹屾暣鍚嶏紝姣斿 openai/openai-python
    # unique=True 琛ㄧず鏁版嵁搴撻噷涓嶈兘閲嶅鐩戞帶鍚屼竴涓粨搴?
    full_name: Mapped[str] = mapped_column(String(511), nullable=False, unique=True)

    # GitHub 椤甸潰鍦板潃锛屾瘮濡?https://github.com/openai/openai-python
    html_url: Mapped[str] = mapped_column(Text, nullable=False)

    # 椤圭洰涓婚〉锛屾湁浜涗粨搴撴病鏈夛紝鎵€浠ュ厑璁镐负绌?
    homepage: Mapped[str | None] = mapped_column(Text)

    # 浠撳簱鎻忚堪锛屾湁浜涗粨搴撲篃鍙兘娌℃湁锛屾墍浠ュ厑璁镐负绌?
    description: Mapped[str | None] = mapped_column(Text)

    # 涓昏瑷€锛屾瘮濡?Python銆乀ypeScript銆丟o
    primary_language: Mapped[str | None] = mapped_column(String(100))

    # topics 鏄?JSON 鏁扮粍锛屾瘮濡?["ai", "python", "sdk"]
    #
    # 涓轰粈涔堢敤 MutableList.as_mutable(JSON)锛?
    # 鏅€?JSON 瀛楁濡傛灉浣犺繖鏍锋敼锛?
    # repo.topics.append("ai")
    # SQLAlchemy 鍙兘涓嶇煡閬撳畠鍙樹簡銆?
    #
    # MutableList 鍙互璁?SQLAlchemy 鎰熺煡鍒楄〃鍐呴儴鍙樺寲銆?
    topics: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON),
        nullable=False,
        default=list,
    )

    # 璁稿彲璇佸悕绉帮紝姣斿 MIT銆丄pache-2.0
    license_name: Mapped[str | None] = mapped_column(String(255))

    # 褰撳墠 stars 鏁?
    stars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # 褰撳墠 forks 鏁?
    forks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # 褰撳墠 watchers 鏁?
    watchers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # 褰撳墠 open issues 鏁?
    open_issues: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # 鏄惁褰掓。
    # MySQL 閲屾槸 TINYINT(1)锛孫RM 閲屽彲浠ュ啓鎴?Boolean
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # 鏄惁涓嶅彲鐢?
    disabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # 鏄惁鍚敤鐩戞帶
    # 浠ュ悗濡傛灉浣犳殏鍋滄煇涓粨搴擄紝灏辨妸 enabled 鏀规垚 False
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # 浠撳簱鏉ユ簮锛屾瘮濡?manual銆乬ithub_search銆乼opic
    source: Mapped[str] = mapped_column(String(100), nullable=False, default="manual")

    # 鏈湴鏍囩锛屾瘮濡?["ai", "sdk"]
    tags: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON),
        nullable=False,
        default=list,
    )

    # GitHub 涓婄殑鍒涘缓鏃堕棿
    github_created_at: Mapped[datetime | None] = mapped_column(DateTime)

    # GitHub 涓婄殑鏇存柊鏃堕棿
    github_updated_at: Mapped[datetime | None] = mapped_column(DateTime)

    # 鏈€杩?push 鏃堕棿
    last_pushed_at: Mapped[datetime | None] = mapped_column(DateTime)

    # 鏈郴缁熸渶杩戜竴娆￠噰闆嗘椂闂?
    last_collected_at: Mapped[datetime | None] = mapped_column(DateTime)

    # 鏈郴缁熷垱寤鸿繖鏉¤褰曠殑鏃堕棿
    #
    # server_default=func.now() 琛ㄧず锛?
    # 濡傛灉 Python 娌′紶 created_at锛屽氨璁╂暟鎹簱鑷姩濉綋鍓嶆椂闂淬€?
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    # 鏈郴缁熸洿鏂拌繖鏉¤褰曠殑鏃堕棿
    #
    # onupdate=func.now() 琛ㄧず锛?
    # ORM 鏇存柊杩欐潯璁板綍鏃讹紝鑷姩鍒锋柊 updated_at銆?
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # relationship 琛ㄧず鈥滃璞′箣闂寸殑鍏崇郴鈥?
    #
    # 涓€涓?Repository 鍙互鏈夊鏉?StarSnapshot銆?
    #
    # 浠ュ悗浣犲彲浠ヨ繖鏍疯闂細
    # repo.snapshots
    #
    # back_populates 瑕佸拰 StarSnapshot 閲岀殑 repository 瀵瑰簲銆?
    snapshots: Mapped[list["StarSnapshot"]] = relationship(
        back_populates="repository",
        cascade="all, delete-orphan",
    )


class StarSnapshot(Base):
    """
    star_snapshots 琛ㄧ殑 ORM 妯″瀷銆?

    杩欏紶琛ㄧ敤鏉ヤ繚瀛樻煇涓粨搴撳湪鏌愪釜鏃堕棿鐐圭殑 stars 蹇収銆?
    姣斿锛?
    2026-06-02 10:00锛宱penai/openai-python 鏈?25000 stars銆?
    """

    __tablename__ = "star_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)

    # repository_id 鏄閿紝鎸囧悜 repositories.id
    #
    # ForeignKey 鐨勪綔鐢細
    # 淇濊瘉杩欐潯蹇収涓€瀹氬睘浜庢煇涓瓨鍦ㄧ殑浠撳簱銆?
    #
    # ondelete="CASCADE" 琛ㄧず锛?
    # 濡傛灉鏌愪釜浠撳簱琚垹闄わ紝瀹冪殑蹇収涔熶竴璧峰垹闄ゃ€?
    repository_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("repositories.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )

    stars: Mapped[int] = mapped_column(Integer, nullable=False)
    forks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    watchers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    open_issues: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # 鏁版嵁鏉ユ簮锛岄粯璁ゆ潵鑷?GitHub REST API
    source: Mapped[str] = mapped_column(String(100), nullable=False, default="github_rest")

    # 蹇収鏃堕棿
    # 濡傛灉 Python 娌′紶锛屽氨璁╂暟鎹簱濉綋鍓嶆椂闂?
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

    # 鍙嶅悜鍏崇郴锛氳繖鏉″揩鐓у睘浜庡摢涓粨搴?
    #
    # 浠ュ悗浣犲彲浠ヨ繖鏍疯闂細
    # snapshot.repository
    repository: Mapped[Repository] = relationship(back_populates="snapshots")

    # 澶嶅悎鍞竴绾︽潫
    #
    # 琛ㄧず鍚屼竴涓粨搴撳湪鍚屼竴涓?snapshot_at 鏃堕棿鐐瑰彧鑳芥湁涓€鏉″揩鐓с€?
    # 杩欐牱鍙互閬垮厤閲嶅閲囬泦鏃舵彃鍏ラ噸澶嶆暟鎹€?
    __table_args__ = (
        UniqueConstraint(
            "repository_id",
            "snapshot_at",
            name="uq_star_snapshots_repo_time",
        ),
    )


class Job(Base):
    """
    jobs 琛ㄧ殑 ORM 妯″瀷銆?

    杩欏紶琛ㄧ敤鏉ヨ褰曞紓姝ヤ换鍔℃垨鎵嬪姩瑙﹀彂浠诲姟銆?
    姣斿锛?
    - GitHub 浠撳簱閲囬泦浠诲姟
    - 鏄熸爣蹇収浠诲姟
    - 鐑偣椤圭洰璁＄畻浠诲姟
    - 閭欢鍙戦€佷换鍔?
    """

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)

    # 鏁版嵁搴撳瓧娈靛悕鍙?type銆?
    #
    # 浣嗘槸 Python 閲?type 鏄唴缃嚱鏁板悕銆?
    # 涓轰簡閬垮厤娣锋穯锛孭ython 灞炴€у悕鐢?job_type锛?
    # 浣?mapped_column("type") 琛ㄧず瀹冨疄闄呭搴旀暟鎹簱閲岀殑 type 瀛楁銆?
    job_type: Mapped[str] = mapped_column("type", String(50), nullable=False)

    # 浠诲姟鐘舵€侊細
    # pending    绛夊緟鎵ц
    # running    鎵ц涓?
    # succeeded  鎵ц鎴愬姛
    # failed     鎵ц澶辫触
    # cancelled  宸插彇娑?
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")

    # 浠诲姟鍙傛暟
    #
    # 姣斿鎵嬪姩瑙﹀彂鏄熸爣蹇収鏃讹紝鍙互淇濆瓨锛?
    # {
    #   "repository_ids": ["xxx"],
    #   "force": false
    # }
    payload: Mapped[dict] = mapped_column(
        MutableDict.as_mutable(JSON),
        nullable=False,
        default=dict,
    )

    # 浠诲姟杩涘害
    #
    # 姣斿锛?
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

    # 閿欒淇℃伅
    # 浠诲姟澶辫触鏃跺彲浠ヨ褰曞紓甯稿師鍥?
    error_message: Mapped[str | None] = mapped_column(Text)

    # 浠诲姟寮€濮嬫椂闂?
    started_at: Mapped[datetime | None] = mapped_column(DateTime)

    # 浠诲姟缁撴潫鏃堕棿
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
