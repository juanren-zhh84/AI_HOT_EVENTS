from datetime import datetime, UTC, timedelta, date

from sqlalchemy import delete,select
from sqlalchemy.orm import Session

from app.db.models import Job, Repository, StarSnapshot, HotProject


class HotProjectService:
    """根据 star_snapshots计算热点项目，并写入hot_projects表"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def calculate_hot_projects(self, report_date, top_n, include_disabled) -> dict:
        """
        手动计算某一天的热点项目
        :param report_date: 榜单日期，None表示今天
        :param top_n: 生成前多少条
        :param include_disabled:是否包含暂停监控的仓库
        :return:返回dict，FastAPI会按照response_model转成json
        """
        current_report_date = report_date or datetime.now(UTC).date()  # 不传日期时使用当前的UTC日期
        calculated_at = datetime.now(UTC)

        job = Job(
            job_type="hot_project_calculate",
            status="running",
            payload={
                "report_date": current_report_date.isoformat(), # date 对象不能直接写入 JSON，所以转成 "2026-06-30" 这种字符串。
                "top_n": top_n,
                "include_disabled": include_disabled
            },
            progress={"total_candidates": 0, "generated": 0},
            started_at=calculated_at,
        )

        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)

        repositories = self._load_repositories(include_disabled)  # 查询参与计算的仓库
        candidates = []  # 保存计算出来的候选项目

        for repository in repositories:
            latest_snapshot = self._get_latest_snapshot(repository.id, calculated_at)  # 查询最新快照
            if latest_snapshot is None:
                continue

            snapshot_24h = self._get_snapshot_before(repository.id, latest_snapshot.snapshot_at - timedelta(hours=24))
            snapshot_7d = self._get_snapshot_before(repository.id, latest_snapshot.snapshot_at - timedelta(days=7))

            stars_delta_24h = self._calculate_delta(latest_snapshot, snapshot_24h)  # 计算 24 小时增长。
            stars_delta_7d = self._calculate_delta(latest_snapshot, snapshot_7d)  # 计算 7 天增长。
            growth_rate_24h = self._calculate_growth_rate(latest_snapshot, snapshot_24h)  # 计算 24 小时增长率。
            hot_score = self._calculate_hot_score(latest_snapshot.stars, stars_delta_24h, stars_delta_7d,growth_rate_24h)  # 计算热度分。

            candidates.append(  # 把候选项目加入列表，后面统一排序。
                {
                    "repository": repository,  # 保存仓库对象，方便写入 repository_id 和返回 full_name。
                    "latest_snapshot": latest_snapshot,  # 保存最新快照，方便读取当前 stars。
                    "stars_delta_24h": stars_delta_24h,  # 保存 24 小时增长。
                    "stars_delta_7d": stars_delta_7d,  # 保存 7 天增长。
                    "growth_rate_24h": growth_rate_24h,  # 保存 24 小时增长率。
                    "hot_score": hot_score,  # 保存热度分。
                }
            )

        candidates.sort(key=lambda item: item["hot_score"], reverse=True)  # 按热度分从高到低排序。
        top_candidates = candidates[:top_n]  # 只取前 top_n 个。

        self._delete_old_report(current_report_date)  # 删除同一天旧榜单，避免唯一约束冲突。

        hot_projects = []  # 保存本次写入的热点项目 ORM 对象。
        for index, candidate in enumerate(top_candidates, start=1):  # 从 1 开始生成排名。
            repository = candidate["repository"]  # 取出仓库对象。
            latest_snapshot = candidate["latest_snapshot"]  # 取出最新快照。

            hot_project = HotProject(  # 创建 hot_projects 表记录。
                repository_id=repository.id,  # 关联仓库 id。
                report_date=current_report_date,  # 保存榜单日期。
                rank_no=index,  # 保存排名。
                hot_score=round(candidate["hot_score"], 4),  # 保存热度分，保留 4 位小数。
                stars=latest_snapshot.stars,  # 保存当前总 star。
                stars_delta_24h=candidate["stars_delta_24h"],  # 保存 24 小时增长。
                stars_delta_7d=candidate["stars_delta_7d"],  # 保存 7 天增长。
                growth_rate_24h=round(candidate["growth_rate_24h"], 6),  # 保存增长率，保留 6 位小数。
                reason=self._build_reason(candidate),  # 生成人能看懂的入选原因。
            )
            self.db.add(hot_project)  # 加入数据库会话。
            hot_projects.append(hot_project)  # 保存对象，后面返回给接口。

        job.status = "succeeded"  # 能走到这里说明计算成功。
        job.progress = {"total_candidates": len(candidates), "generated": len(hot_projects)}  # 更新任务进度。
        job.finished_at = datetime.now(UTC)  # 记录结束时间。
        self.db.commit()  # 提交热点榜单和任务状态。

        for hot_project in hot_projects:  # 遍历本次写入的热点项目。
            self.db.refresh(hot_project)  # 刷新对象，拿到 created_at、updated_at 等数据库生成字段。

        return {  # 返回接口需要的数据。
            "job_id": job.id,  # 返回任务 id。
            "status": job.status,  # 返回任务状态。
            "report_date": current_report_date,  # 返回榜单日期。
            "total_candidates": len(candidates),  # 返回候选数。
            "generated": len(hot_projects),  # 返回生成数量。
            "hot_projects": [self._to_response_dict(item) for item in hot_projects],  # 转成接口响应结构。
        }

    def list_hot_projects(self, report_date: date | None = None, limit: int = 20) -> list[dict]:  # 查询某天热点榜单。
        current_report_date = report_date or datetime.now(UTC).date()  # 不传日期时查询今天。
        statement = (  # 构造查询语句。
            select(HotProject)  # 查询 hot_projects 表。
            .where(HotProject.report_date == current_report_date)  # 只查指定日期。
            .order_by(HotProject.rank_no.asc())  # 按排名升序。
            .limit(limit)  # 限制返回数量。
        )
        hot_projects = list(self.db.scalars(statement).all())  # 执行查询并转成 list。
        return [self._to_response_dict(item) for item in hot_projects]  # 转成响应字典列表。


    def _load_repositories(self, include_disabled):
        """
        查询参与热点计算的仓库。
        :param include_disabled: 是否包含暂停监控的仓库
        :return: 返回仓库列表
        """
        statement = select(Repository) # 查询repositories表
        if not include_disabled: # 默认不包含暂停监控的仓库
            statement = statement.where(Repository.enabled.is_(True)) # 只读取enabled = True的仓库
        statement = statement.where(Repository.archived.is_(False))  # 归档仓库通常不适合作为热点推荐。
        statement = statement.where(Repository.disabled.is_(False))  # GitHub 禁用仓库不参与热点计算。
        statement = statement.order_by(Repository.stars.desc())  # 先按 stars 排序，方便稳定处理。
        return list(self.db.scalars(statement).all())  # 返回仓库列表。

    def _get_latest_snapshot(self, repository_id: str, before_time: datetime) -> StarSnapshot | None:
        """
        查询某仓库最新快照
        """
        statement = (  # 构造查询语句。
            select(StarSnapshot)  # 查询 star_snapshots 表。
            .where(StarSnapshot.repository_id == repository_id)  # 只查当前仓库。
            .where(StarSnapshot.snapshot_at <= before_time)  # 只取计算时间之前的快照。
            .order_by(StarSnapshot.snapshot_at.desc())  # 最新的排最前。
            .limit(1)  # 只要一条。
        )
        return self.db.scalar(statement)  # 查到返回 StarSnapshot，查不到返回 None。

    def _get_snapshot_before(self, repository_id: str, target_time: datetime) -> StarSnapshot | None:
        """
        查询目标时间之前最近快照。
        """
        statement = (  # 构造查询语句。
            select(StarSnapshot)  # 查询 star_snapshots 表。
            .where(StarSnapshot.repository_id == repository_id)  # 只查当前仓库。
            .where(StarSnapshot.snapshot_at <= target_time)  # 找目标时间点之前的快照。
            .order_by(StarSnapshot.snapshot_at.desc())  # 离目标时间最近的排最前。
            .limit(1)  # 只取一条。
        )
        return self.db.scalar(statement)  # 查到返回 StarSnapshot，查不到返回 None。

    def _calculate_delta(self, latest_snapshot: StarSnapshot, old_snapshot: StarSnapshot | None) -> int:
        if old_snapshot is None: # 如果没有历史快照
            return 0 # 无法计算增长，先按0处理
        return max(latest_snapshot.stars - old_snapshot.stars,0) # 增长不允许为负，避免 GitHub 异常或数据回退影响排序。

    def _calculate_growth_rate(self, latest_snapshot: StarSnapshot, old_snapshot: StarSnapshot | None) -> float:
        """
        计算24小时增长率
        """
        if old_snapshot is None: return 0.0
        if old_snapshot.stars <= 0: return 0.0
        return max((latest_snapshot.stars - old_snapshot.stars)/old_snapshot.stars,0.0) # 只保正增长率


    def _calculate_hot_score(self, stars: int, delta_24h: int, delta_7d: int, growth_rate_24h: float) -> float:
        """
        # 计算热度分。
        """
        star_base_score = min(stars, 100000) * 0.001  # 总 stars 给少量基础分，避免老项目完全没权重。
        daily_growth_score = delta_24h * 5  # 24 小时增长权重最高，因为它最能代表“今天热”。
        weekly_growth_score = delta_7d * 1  # 7 天增长权重较低，用来补充趋势。
        growth_rate_score = growth_rate_24h * 100  # 增长率给额外加分，照顾小而快的项目。
        return star_base_score + daily_growth_score + weekly_growth_score + growth_rate_score  # 返回最终热度分。


    def _build_reason(self, candidate: dict) -> str:  # 生成入选原因。
        delta_24h = candidate["stars_delta_24h"]  # 取出 24 小时增长。
        delta_7d = candidate["stars_delta_7d"]  # 取出 7 天增长。
        hot_score = candidate["hot_score"]  # 取出热度分。
        return f"近24小时新增 {delta_24h} stars，近7天新增 {delta_7d} stars，热度分 {hot_score:.2f}。"  # 返回可读文案。


    def _delete_old_report(self, report_date: date) -> None:  # 删除同一天旧榜单。
        statement = delete(HotProject).where(HotProject.report_date == report_date)  # 构造删除语句。
        self.db.execute(statement)  # 执行删除；等外层 commit 一起提交。


    def _to_response_dict(self, hot_project: HotProject) -> dict:  # 把 ORM 对象转成接口响应字典。
        repository = hot_project.repository  # 通过 ORM 关系拿到仓库对象。
        return {  # 返回响应模型需要的字段。
            "id": hot_project.id,  # 热点记录 id。
            "repository_id": hot_project.repository_id,  # 仓库 id。
            "full_name": repository.full_name,  # 仓库完整名。
            "html_url": repository.html_url,  # GitHub 地址。
            "description": repository.description,  # 仓库描述。
            "primary_language": repository.primary_language,  # 主语言。
            "report_date": hot_project.report_date,  # 榜单日期。
            "rank_no": hot_project.rank_no,  # 排名。
            "hot_score": float(hot_project.hot_score),  # Decimal 转 float，方便 JSON 返回。
            "stars": hot_project.stars,  # 当前总 stars。
            "stars_delta_24h": hot_project.stars_delta_24h,  # 24 小时增长。
            "stars_delta_7d": hot_project.stars_delta_7d,  # 7 天增长。
            "growth_rate_24h": float(hot_project.growth_rate_24h),  # Decimal 转 float。
            "reason": hot_project.reason,  # 入选原因。
            "created_at": hot_project.created_at,  # 创建时间。
            "updated_at": hot_project.updated_at,  # 更新时间。
        }