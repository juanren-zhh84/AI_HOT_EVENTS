from sqlalchemy.orm import Session

from app.db.models import MonitorSource
from app.schemas.monitor_source import MonitorSourceCreate, MonitorSourceUpdate


class MonitorSourceService:
    def __init__(self,db:Session):
        self.db=db

    def create_source(self,pyload: MonitorSourceCreate) -> MonitorSource:
        source=MonitorSource(
            name=pyload.name,
            source_type=pyload.source_type,
            query=pyload.query,
            filters=pyload.filters,
            enabled=pyload.enabled,
            discover_interval_minutes=pyload.discover_interval_minutes,
        )
        self.db.add(source)
        self.db.commit()
        self.db.refresh(source)
        return source

    def list_sources(self):  # 查询全部监控源。
        return self.db.query(MonitorSource).order_by(MonitorSource.created_at.desc()).all()  # 按创建时间倒序返回，最新配置排在前面。

    def get_source(self, source_id: str): # 获取单个监控源
        return self.db.get(MonitorSource, source_id)

    def update_source(self, source_id: str, pyload: MonitorSourceUpdate): # 更新监控源
        source=self.get_source(source_id) # 先查询目标记录
        if not source:
            return None
        update_data = pyload.model_dump(exclude_unset=True) #只更新用户明确提交的字段，不覆盖其他未提交的字段为默认值
        for field_name, field_value in update_data.items(): # 遍历需要更新的字段
            setattr(source, field_name, field_value) # 动态设置ORM对象字段

        self.db.commit()
        self.db.refresh(source)
        return source
