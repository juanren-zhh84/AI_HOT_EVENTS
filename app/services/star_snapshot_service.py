from datetime import datetime,UTC

import httpx
from sqlalchemy import select  # SQLAlchemy 2.x 推荐用 select 构造查询。
from sqlalchemy.exc import IntegrityError  # 捕获唯一约束冲突等数据库写入错误。
from sqlalchemy.orm import Session  # Session 是数据库会话类型，用来查询和提交事务。

from app.db.models import StarSnapshot, Job, Repository
from app.services.github_client import GitHubClient
from app.services.repository_service import parse_github_datetime


class StarSnapshotService:
    """负责手动采集github仓库指标，并写入star_snapshots"""
    def __init__(self,db:Session) -> None:
        self.db=db
        self.github_client = GitHubClient() # 创建 GitHub 客户端，用来获取最新仓库指标。

    def list_snapshots(self,repository_id: str, limit: int = 20) -> list[StarSnapshot]: # 查询某个仓库的快照列表
        # 构造 SQLAlchemy 查询语句。
        statement = (
            select(StarSnapshot) # 查询 star_snapshots 表对应的 ORM 对象。
            .where(StarSnapshot.repository_id == repository_id)
            .order_by(StarSnapshot.snapshot_at.desc()) # 最新快照排在最前面，方便查看最近采集结果。
            .limit(limit)
        )
        return list(self.db.scalars(statement).all()) # 执行查询并把结果转成普通list返回

    def run_snapshot(self,repository_ids: list[str] | None = None,include_disabled: bool = False,) -> dict:
        normalized_ids = self._normalize_repository_ids(repository_ids) # 清理id列表，去空格并去重
        started_at = datetime.now(UTC)
        # 创建一条任务记录，记录这次采集过程
        job = Job(
            job_type="star_snapshot",
            status="running", # 刚开始执行，所以是running
            payload={ # 保存本次任务参数，方便以后排查
                "repository_ids": normalized_ids,
                "include_disabled": include_disabled,
            },
            progress={"total":0,"succeeded":0,"failed":0},# 初始化任务进度
            started_at=started_at, # 保存开始时间
        )
        self.db.add(job) # 把任务对象加入数据库会话
        self.db.commit() # 提交任务记录
        self.db.refresh(job) # 刷新

        repositories =  self._load_target_repositories(normalized_ids,include_disabled)
        errors = self._build_skipped_errors(normalized_ids,repositories)

        snapshots: list[StarSnapshot] = [] # 保存本次成功写入的快照对象
        succeeded_count = 0
        failed_count = len(errors) # 失败计数先包含不存在的或者被跳过的仓库
        total_count = len(normalized_ids) if normalized_ids is not None else len(repositories) # 指定 id 时按请求数量统计，否则按查询到的仓库数量统计。

        for repository in repositories:
            try:
                github_data = self.github_client.get_repository(repository.owner,repository.name) # 获取 GitHub 最新仓库数据。
                snapshot_at = datetime.now(UTC) # 记录这次快照采集的时间

                self._sync_repository_metrics(repository,github_data,snapshot_at) # 同步repositories表里的当前指标
                snapshot = self._create_snapshot(repository,snapshot_at) # 根据当前仓库指标创建 StarSnapshot 对象

                self.db.add(snapshot)
                self.db.commit()
                self.db.refresh(snapshot)
                snapshots.append(snapshot)
                succeeded_count += 1

            except httpx.HTTPError as exc: # 捕获 GitHub HTTP 错误或网络错误。
                self.db.rollback()
                errors.append({
                    "repository_id": repository.id,
                    "full_name": repository.full_name,
                    "error_message": self._format_http_error(repository,exc),
                })

            except IntegrityError as exc:
                self.db.rollback()
                failed_count += 1
                errors.append({
                    "repository_id": repository.id,
                    "full_name": repository.full_name,
                    "error_message": f"写入 star_snapshots 失败：{exc.orig}",  # 记录底层数据库错误。
                })

        job.status = "succeeded" if failed_count == 0 else "failed" # 只要有失败就把任务标记为failed，方便排查
        job.progress = {"total": total_count,"succeeded":succeeded_count,"failed":failed_count}
        job.error_message = self._join_error_messages(errors)  # 把错误列表压缩成文本，保存到 jobs.error_message。
        job.finished_at = datetime.now(UTC)  # 记录任务结束时间。
        self.db.commit()  # 提交任务最终状态。
        self.db.refresh(job)  # 刷新任务对象，确保返回的是数据库最终状态。

        return {  # 返回接口响应需要的数据。
            "job_id": job.id,  # 返回任务 id。
            "status": job.status,  # 返回任务状态。
            "total": total_count,  # 返回总数。
            "succeeded": succeeded_count,  # 返回成功数。
            "failed": failed_count,  # 返回失败数。
            "snapshots": snapshots,  # 返回成功快照列表。
            "errors": errors,  # 返回失败明细。
        }




    # 清理请求里的仓库id
    def _normalize_repository_ids(self, repository_ids: list[str] | None = None) -> list[str] | None:
        # 如果用户没有指定仓库id
        if repository_ids is None:
            return None # 保留None，后续使用它表示“采集所有启用仓库”

        normalized_ids: list[str] = []
        for repository_id in repository_ids: # 遍历用户传入的每个id
            clean_id = repository_id.strip()
            if clean_id and clean_id not in normalized_ids: # 空字符串不要，重复id只保留一次
                normalized_ids.append(clean_id) # 保存有效id
        return normalized_ids

    # 查询本次需要采集的仓库
    def _load_target_repositories(self, repository_ids: list[str] | None, include_disabled: bool) -> list[Repository]:
        statement = select(Repository)
        if repository_ids is not None:# 用户传了 repository_ids 字段。
            if not repository_ids:# 但这个列表是空的。
                return [] # 直接返回空结果。不查数据库
            statement = statement.where(Repository.id.in_(repository_ids)) # 否则查询这些id对应仓库

        if not include_disabled: # 默认不采集已暂停监控的仓库
            statement = statement.where(Repository.enabled == True) # 只保留 enable=true的仓库

        statement = statement.order_by(Repository.created_at.asc())
        repositories = list(self.db.scalars(statement).all()) # 查询，得到仓库列表

        # 如果不是指定id,直接返回全部目标仓库
        if repository_ids is None:
            return repositories

        repository_map = {repository.id: repository for repository in repositories} # 建立 id ——> 仓库对象的映射
        return[repository_map[repository_id] for repository_id in repository_ids if repository_id in repository_map]



    def _build_skipped_errors(self, repository_ids: list[str], repositories: list[Repository]) -> list[dict]:
        """
        生成“没查到或被跳过”的错误列表
        :param repository_ids: 用户指定的仓库id
        :param repositories: 实际查到并准备采集的仓库
        :return: 返回错误的dict列表
        """
        if repository_ids is None:
            return []

        select_ids = {repository.id for repository in repositories}  # 实际被采集的仓库id的集合
        errors: list[dict] = []
        for repository_id in repository_ids:
            if repository_id not in select_ids: # 如果id没有进入采集列表
                errors.append({
                    "repository_id": repository_id,
                    "full_name": None,
                    "error_message": "仓库不存在，或该仓库已暂停监控且 include_disabled=false。"
                })

        return errors

    def _sync_repository_metrics(self, repository, github_data, collected_at: datetime):
        """
        # 把 GitHub 最新指标同步回 repositories 表。
        :param repository: 当前要更新的仓库对象
        :param github_data: Github API返回的仓库详情
        :param collected_at: 本次采集时间
        :return: 只修改ORM对象，不直接返回值
        """
        repository.stars = github_data.get("stargazers_count") or 0  # 更新当前 star 数。
        repository.forks = github_data.get("forks_count") or 0  # 更新当前 fork 数。
        repository.watchers = github_data.get("watchers_count") or 0  # 更新当前 watcher 数。
        repository.open_issues = github_data.get("open_issues_count") or 0  # 更新当前 open issue 数。
        repository.archived = github_data.get("archived") or False  # 更新 GitHub 是否归档。
        repository.disabled = github_data.get("disabled") or False  # 更新 GitHub 是否禁用。
        repository.primary_language = github_data.get("language")  # 更新主语言，方便后续热点筛选。
        repository.topics = github_data.get("topics") or []  # 更新 GitHub topics，None 时保存空列表。
        repository.github_updated_at = parse_github_datetime(github_data.get("updated_at"))  # 更新 GitHub 更新时间。
        repository.last_pushed_at = parse_github_datetime(github_data.get("pushed_at"))  # 更新最近 push 时间。
        repository.last_collected_at = collected_at  # 更新本系统最近采集时间。

    def _create_snapshot(self, repository, snapshot_at): # 创建快照ORM对象
        return StarSnapshot(  # 返回一条还没提交数据库的快照对象。
            repository_id=repository.id,  # 关联当前仓库 id。
            stars=repository.stars,  # 保存本次采集到的 star 数。
            forks=repository.forks,  # 保存本次采集到的 fork 数。
            watchers=repository.watchers,  # 保存本次采集到的 watcher 数。
            open_issues=repository.open_issues,  # 保存本次采集到的 open issue 数。
            source="github_rest",  # 标记数据来源为 GitHub REST API。
            snapshot_at=snapshot_at,  # 保存快照采集时间。
        )

    def _format_http_error(self, repository: Repository, exc: httpx.HTTPError) -> str:  # 把 httpx 异常转成易懂文案。
        if isinstance(exc, httpx.HTTPStatusError):  # HTTPStatusError 表示 GitHub 返回了 4xx/5xx。
            status_code = exc.response.status_code  # 取出 HTTP 状态码。
            if status_code == 404:  # 404 表示 GitHub 上找不到这个仓库。
                return f"GitHub 仓库不存在：{repository.full_name}"  # 返回更明确的提示。
            if status_code == 403:  # 403 常见原因是 token 权限不足或 API 限流。
                return f"GitHub API 拒绝访问或限流：{repository.full_name}"  # 返回限流/权限提示。
            return f"GitHub API 请求失败，状态码 {status_code}：{repository.full_name}"  # 其他状态码统一说明。
        return f"请求 GitHub 失败：{repository.full_name}，原因：{exc}"  # 网络错误、超时等走这里。

    def _join_error_messages(self, errors: list[dict]) -> str | None:  # 把错误列表合并成 jobs.error_message。
        if not errors:  # 如果没有错误。
            return None  # 数据库错误字段保存为空。
        return "\n".join(error["error_message"] for error in errors)  # 多个错误用换行拼起来，方便查看。


