import re  # 关键词按词边界匹配用正则。
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.db.models import Job, MonitorSource, Repository
from app.schemas.discovery import DiscoveryRunRequest
from app.services.github_client import GitHubClient
from app.services.repository_service import parse_github_datetime

AI_AGENT_KEYWORDS = {  # AI/Agent 关键词集合。
    "ai", "agent", "llm", "rag", "chatbot", "workflow",  # 常见能力词。
    "automation", "multi-agent", "openai", "langchain", "llama",  # 常见生态词。
}

class DiscoveryService:
    """自动发现业务服务"""
    def __init__(self, db:Session):
        self.db = db
        self.github = GitHubClient()

    def run_discovery(self, payload: DiscoveryRunRequest) -> dict:
        job = Job(job_type="discovery", status="running", payload=payload.model_dump(), started_at=datetime.now(timezone.utc))
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)

        counters = {
            "source_count": 0,  # 执行的监控源数量。
            "discovered_count": 0,  # 拉到的候选仓库数量。
            "inserted_count": 0,  # 新增仓库数量。
            "updated_count": 0,  # 更新仓库数量。
            "skipped_count": 0,  # 跳过仓库数量。
        }

        try:
            sources = self._load_sources(payload.source_id) # 加载需要执行的监控源
            counters["source_count"] += len(sources) # 记录监控源数量
            for source in sources:
                self._run_source(source, payload.max_pages, payload.per_page, counters) # 执行单个监控源
                source.last_discovered_at = datetime.now(timezone.utc) # 更新监控源最近执行时间
            job.status = "succeeded" # 全部执行成功后标记成功
            job.progress = counters # 把统计数据写进任务进度
            job.finished_at = datetime.now(timezone.utc) # 记录任务结束时间
            self.db.commit()
        except Exception as exc:
            self.db.rollback()  # 先回滚失败事务
            job = self.db.get(Job, job.id)
            job.status = "failed"
            job.error_message = str(exc)
            job.progress = counters # 保存已完成的进度
            job.finished_at = datetime.now(timezone.utc) # 记录失败时间、
            self.db.commit()
            raise # 继续抛出异常，让路由层返回错误

        return{
            "job_id": job.id,
            "status": job.status,
            **counters,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
        }

    def _load_sources(self,source_id):
        """加载监控源。"""
        query = self.db.query(MonitorSource).filter(MonitorSource.enabled.is_(True)) # 默认只执行启用的监控源。
        if source_id:
            query = query.filter(MonitorSource.id == source_id) # 只查询指定id
        return query.all()

    def _run_source(self, source, max_pages, per_page, counters):
        """执行单个监控源"""
        # 按页拉取Github数据
        for page in range(1, max_pages + 1):
            repositories = self._fetch_page(source, page, per_page)
            counters["discovered_count"] += len(repositories) # 累计候选数量
            for github_data in repositories: # 遍历候选仓库
                # 如果不符合过滤规则
                if not self._is_candidate_repository(github_data, source.filters):
                    counters["skipped_count"] += 1
                    continue # 进入下一个仓库
                inserted = self._upsert_repository(github_data,source) # 写入或更新仓库
                if inserted:
                    counters["inserted_count"] += 1
                else:
                    counters["updated_count"] += 1

    def _fetch_page(self, source, page, per_page):
        """根据监控源类型拉取一页仓库。"""
        if source.source_type == "github_search":
            result = self.github.search_repositories(source.query, page=page, per_page=per_page)  #调用搜索接口
            return result.get("items",[])  #Search API返回items
        if source.source_type in {"topic","manual"}: # topic和manual都可以转成search查询
            result = self.github.search_repositories(source.query, page=page, per_page=per_page)
            return result.get("items",[])
        if source.source_type == "owner":
            return self.github.list_owner_repositories(source.query, page=page, per_page=per_page) # 拉取owner仓库
        return [] # 未知类型直接返回空列表，避免任务崩溃。

    def _is_candidate_repository(self, github_data, filters):
        """判断仓库是否值得入库"""
        min_stars = filters.get("min_stars",100)  # 最低star门槛，默认100
        if github_data.get("stargazers_count",0) < min_stars:
            return False # 如果star不达标，跳过该仓库
        if github_data.get("archived") or github_data.get("disabled"):
            return False # 如果已归档或禁用
        keywords = self._parse_keywords(filters.get("keywords"))  # 读取关键词过滤列表
        if keywords:  # 配置了关键词才过滤
            name_desc_text = " ".join([  # 仓库名+描述是自由文本，短词按子串匹配容易误中（如 ai 命中 maintain），按词边界匹配
                github_data.get("full_name") or "",
                github_data.get("description") or "",
            ]).lower()  # 统一转小写
            topics_text = " ".join(github_data.get("topics") or []).lower()  # topics 是 GitHub 精确标签（如 ai-agents），按子串匹配即可
            if not any(self._keyword_matches(keyword, name_desc_text, topics_text) for keyword in keywords):  # 命中任意一个关键词才算通过
                return False  # 一个都没命中，跳过该仓库
        return True

    def _keyword_matches(self, keyword, name_desc_text, topics_text):
        """关键词命中判断，避免 ai、go 等短词误中 maintain、google 等无关文本：
        1. 英文/数字关键词：对仓库名+描述按词边界匹配，并兼容 agents 等复数形式；
        2. topics：GitHub 标签是精确词（如 ai-agents），词边界会漏掉，按子串匹配；
        3. 纯中文关键词没有词边界概念，退化为子串匹配（如"智能"命中"人工智能"）。
        """
        if re.search(r"[a-z0-9]", keyword):  # 关键词含英文或数字
            pattern = r"\b" + re.escape(keyword) + r"s?\b"  # 词边界 + 可选复数 s
            if re.search(pattern, name_desc_text):  # 仓库名/描述命中
                return True  # 命中返回 True
            return keyword in topics_text  # 未命中则看 topics 子串
        return keyword in name_desc_text or keyword in topics_text  # 纯中文退化为子串匹配

    def _parse_keywords(self, raw_keywords):
        """把 filters.keywords 标准化成小写关键词列表，兼容字符串和列表两种写法"""
        if not raw_keywords:  # 未配置或空值
            return []  # 返回空列表表示不过滤
        if isinstance(raw_keywords, str):  # 兼容逗号分隔字符串，例如 "agent, rag"
            raw_keywords = [part.strip() for part in raw_keywords.split(",") if part.strip()]
        keywords = []  # 初始化结果列表
        for keyword in raw_keywords:  # 遍历原始关键词
            keyword = str(keyword).strip().lower()  # 统一转小写并去掉空白
            if keyword:  # 跳过空字符串
                keywords.append(keyword)  # 加入结果列表
        return keywords  # 返回标准化关键词列表

    def _build_local_tags(self,github_data):
        """生成系统内部标签"""
        text_parts = [ # 收集待匹配的文本
            github_data.get("full_name") or "",
            github_data.get("description") or "",
            " ".join(github_data.get("topics") or []),
        ]
        searchable_text = " ".join(text_parts).lower()
        tags: list[str] = [] # 初始化标签列表
        if any(keyword in searchable_text for keyword in AI_AGENT_KEYWORDS):
            tags.append("AI") # 命中AI关键词就增加AI标签
        if "agent" in searchable_text or "multi-agent" in searchable_text:
            tags.append("Agent") # 如果命中Agent关键词就增加Agent标签
        return tags # 返回标签列表

    def _upsert_repository(self, github_data, source):
        """新增或更新仓库"""
        full_name = github_data["full_name"]
        repository = self.db.query(Repository).filter(Repository.full_name == full_name).first() # 查找是否已存在
        inserted = repository is None # 是否为新增记录
        if repository is None:
            owner, name = full_name.split("/")
            repository = Repository(owner=owner, name=name, full_name=full_name, source=source.source_type)
            self.db.add(repository)

        repository.html_url = github_data.get("html_url") or repository.html_url  # 更新 GitHub 页面地址。
        repository.homepage = github_data.get("homepage")  # 更新项目主页。
        repository.description = github_data.get("description")  # 更新描述。
        repository.primary_language = github_data.get("language")  # 更新主语言。
        repository.topics = github_data.get("topics") or []  # 更新 GitHub topics。
        repository.license_name = (github_data.get("license") or {}).get("name")  # 更新许可证名称。
        repository.stars = github_data.get("stargazers_count", 0)  # 更新 stars。
        repository.forks = github_data.get("forks_count", 0)  # 更新 forks。
        repository.watchers = github_data.get("watchers_count", 0)  # 更新 watchers。
        repository.open_issues = github_data.get("open_issues_count", 0)  # 更新 open issues。
        repository.archived = github_data.get("archived", False)  # 更新归档状态。
        repository.disabled = github_data.get("disabled", False)  # 更新禁用状态。
        repository.tags = self._build_local_tags(github_data)  # 更新本地 AI/Agent 标签。
        repository.github_created_at = parse_github_datetime(github_data.get("created_at"))
        repository.github_updated_at = parse_github_datetime(github_data.get("updated_at"))
        repository.last_pushed_at = parse_github_datetime(github_data.get("pushed_at"))
        repository.last_collected_at = datetime.utcnow()  # 记录本系统采集时间。
        return inserted  # 返回是否为新增。





