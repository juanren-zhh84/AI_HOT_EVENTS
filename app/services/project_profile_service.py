import hashlib
from datetime import timezone, datetime

from app.db.models import Job, ProjectProfile, Repository
from app.schemas.project_profile import ProjectProfileGenerateRequest
from app.services.github_client import GitHubClient


class ProjectProfileService:
    def __init__(self,db):
        self.db = db
        self.github = GitHubClient()

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
                self.generate_for_repository(repository, force=payload.force)  #生成或更新画像
                generated += 1
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

        profile.summary = self._build_summary(summary_source)  # 生成一句话简介。
        profile.features = self._build_features(summary_source)  # 生成功能点。
        profile.audience = self._build_audience(repository, summary_source)  # 生成适用人群。
        profile.highlights = self._build_highlights(repository, summary_source)  # 生成项目亮点。
        profile.tech_stack = self._build_tech_stack(repository)  # 生成技术栈。

        profile.readme_hash = readme_hash # 保存哈希
        profile.summary_status = "complete" if readme_text else "partial"
        profile.generated_at = datetime.now(timezone.utc)

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

    def _build_summary(self, text):
        """生成一句话简介"""
        clean_text = " ".join(text.split()) # 把多行文本压缩成一行,避免出现大量换行
        return clean_text[:240] if clean_text else None # 截取前 240 字作为最小可用简介。

    def _build_features(self, text):
        """生成项目功能点"""
        lowered = text.lower()
        features = [] # 功能点列表
        if "agent" in lowered:
            features.append("Agent workflow support")
        if "rag" in lowered:
            features.append("Rag workflow support")
        if "workflow" in lowered:
            features.append("Workflow support")
        return features[:5] or ["基于项目简洁的readme或者描述"]

    def _build_audience(self, repository, text):
        """生成适用人群"""
        audience = ["适合AI应用开发者"]
        if repository.primary_language:
            audience.append(f"{repository.primary_language} 开发者") # 增加语言开发者
        return audience

    def _build_highlights(self, repository: Repository, text: str) -> list[str]:  # 生成项目亮点。
        highlights = [f"{repository.stars} GitHub stars"]  # star 数是最直观亮点。
        if repository.tags:  # 如果有本地标签。
            highlights.append(f"Matched tags: {', '.join(repository.tags)}")  # 展示命中标签。
        return highlights  # 返回亮点。

    def _build_tech_stack(self, repository: Repository) -> dict:  # 生成技术栈。
        languages = self.github.get_languages(repository.owner, repository.name)  # 调 GitHub languages API。
        return {"primary_language": repository.primary_language, "languages": languages}  # 返回主语言和语言占比。


