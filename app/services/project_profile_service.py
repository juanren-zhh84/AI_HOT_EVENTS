import hashlib
from datetime import timezone, datetime

from app.db.models import Job, ProjectProfile, Repository
from app.schemas.project_profile import ProjectProfileGenerateRequest
from app.services.github_client import GitHubClient
from app.services.chinese_profile_service import ChineseProfileService


class ProjectProfileService:
    def __init__(self,db):
        self.db = db
        self.github = GitHubClient()
        self.chinese_profile = ChineseProfileService()

    def run_profile_generation(self,payload: ProjectProfileGenerateRequest):
        job = Job(job_type="profile_refresh", status="running", payload=payload.model_dump(), started_at=datetime.now(timezone.utc))
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)

        repositories = self._load_repositories(payload) # 加载需要生成画像的仓库
        generated = 0 # 成功生成数量
        failed = 0 # 失败数量

        for repository in repositories:
            # 单个仓库失败不影响其他仓库
            try:
                result = self.generate_for_repository(repository, force=payload.force)  #生成或更新画像
                if result is None:  # LLM 生成失败（无兜底）
                    failed += 1  # 计入失败数量
                else:
                    generated += 1  # 计入成功数量
            except Exception: # 捕获单个异常
                failed += 1
        job.status = "succeeded" if failed == 0 else "failed" # 全部成功才标记succeeded
        job.progress = {"total":len(repositories), "generated":generated, "failed":failed} # 保存任务进度
        job.finished_at = datetime.now(timezone.utc)
        self.db.commit()

        return {"job_id": job.id, "status": job.status, "total": len(repositories), "generated": generated, "failed": failed}

    def generate_for_repository(self, repository, force=False):
        """为单个仓库生成画像"""
        readme_text = self._load_readme_text(repository)
        summary_source = readme_text or repository.description or ""  # readme缺失时降级到description
        readme_hash = self._hash_text(readme_text) if readme_text else None # readme存在时计算哈希
        profile = repository.profile or ProjectProfile(repository_id=repository.id) # 有画像则更新，没有则新建
        if profile.readme_hash == readme_hash and not force: # readme没变化不强制刷新
            return profile

        chinese_profile = self.chinese_profile.build_profile(  # 调用中文画像服务生成中文展示字段。
            repository=repository,  # 传入仓库 ORM，提供仓库名称、stars、语言等结构化信息。
            readme_text=readme_text,  # 传入 README 原文，优先让大模型理解完整项目说明。
            fallback_text=repository.description or "",  # README 缺失时降级使用 GitHub description。
        )  # 返回 summary、features、audience、highlights、status；LLM 失败时返回 None。

        if chinese_profile is None:  # LLM 生成失败（无兜底）。
            return None  # 不写入画像，跳过该仓库；已有画像保持原样，下次任务自动重试。

        profile.summary = chinese_profile["summary"]  # 写入中文一句话简介，邮件日报会优先展示这个字段。
        profile.features = chinese_profile["features"]  # 写入中文功能点。
        profile.audience = chinese_profile["audience"]  # 写入中文适用人群。
        profile.highlights = chinese_profile["highlights"]  # 写入中文亮点。
        profile.tech_stack = self._build_tech_stack(repository)  # 技术栈继续用 GitHub languages API，不交给大模型猜。

        profile.readme_hash = readme_hash  # 保存 README 哈希，用来判断后续是否需要重新生成。
        profile.summary_status = chinese_profile["status"]  # complete 表示模型生成成功，partial 表示使用了本地兜底。
        profile.generated_at = datetime.now(timezone.utc)  # 保存生成时间。

        self.db.add(profile)
        self.db.commit()
        self.db.refresh(profile)

        return profile

    def get_profile(self,repository_id):
        """查询仓库画像"""
        return self.db.query(ProjectProfile).filter(ProjectProfile.repository_id == repository_id).first()

    def _load_repositories(self, payload):
        """加载待处理的库"""
        query = self.db.query(Repository).filter(Repository.enabled.is_(True)) # 默认只处理启用仓库
        # 如果指定仓库，只处理指定仓库
        if payload.repository_id:
            query = query.filter(Repository.id == payload.repository_id)
        # 如果不是强制刷新，只处理还没有画像的仓库。
        if not payload.force:
            query = query.outerjoin(ProjectProfile).filter(ProjectProfile.id.is_(None))
        return query.limit(payload.limit).all()# 限制单次处理数量

    def _load_readme_text(self, repository):
        """读取 README 文本"""
        readme = self.github.get_readme(repository.owner, repository.name)
        if not readme:
            return None
        content = readme.get("content") or ""
        import base64
        decoded = base64.b64decode(content).decode("utf-8", errors="ignore") # 解码为utf-8文本
        return decoded

    def _hash_text(self, text):
        """计算文本哈希"""
        return hashlib.sha256(text.encode("utf-8")).hexdigest() # 使用SHA256生成稳定哈希

    def _build_tech_stack(self, repository: Repository) -> dict:  # 生成技术栈。
        languages = self.github.get_languages(repository.owner, repository.name)  # 调 GitHub languages API。
        return {"primary_language": repository.primary_language, "languages": languages}  # 返回主语言和语言占比。


