from fastapi import APIRouter, Depends

from app.api.dependencies import require_admin_token
from app.services.github_client import GitHubClient

router = APIRouter(prefix="/github", tags=["github"], dependencies=[Depends(require_admin_token)])  # 当前文件接口统一以 /github 开头。


@router.get("/rate-limit")  # GET /github/rate-limit 查询 GitHub API 限流状态。
def get_github_rate_limit() -> dict:  # 返回 GitHub 原始 rate limit 结构。
    client = GitHubClient()  # 创建 GitHub 客户端。
    return client.get_rate_limit()  # 调用 GitHub /rate_limit 并返回。