
import httpx
from app.core.config import settings

class GitHubClient:

    """
    GitHub API 客户端。

    这个类专门负责和 GitHub REST API 通信。

    为什么要单独封装一个 GitHubClient？
    因为后面很多地方都会用到 GitHub API：

    1. 添加仓库时，要查询仓库详情
    2. 定时采集时，要查询 stars、forks、issues
    3. 生成项目画像时，要查询 README、语言占比
    4. 运维检查时，要查询 rate limit

    如果每个地方都自己写 httpx.get(...)，代码会很乱。
    所以我们把 GitHub 相关请求集中放到这个类里。
    """
    def __init__(self) -> None:
        """
        初始化 GitHubClient。

        这里主要做两件事：

        1. 读取 GitHub API 基础地址
        2. 准备所有请求都要带的 headers

        settings 来自 app/core/config.py，
        它会自动读取 .env 文件里的配置。
        """
        # GitHub API基础地址：https://api.github.com
        self.base_url = settings.github_api_base_url

        # GitHub REST API 推荐的请求头
        # Accept: 告诉 GitHub，我们希望返回官方推荐的 JSON 格式。
        # X-GitHub-Api-Version: 告诉 GitHub 使用哪个 API 版本。这样可以减少未来 API 行为变化带来的风险。
        self.headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": settings.github_api_version,
        }

        # 如果.env中配置了GITHUB_TOKEN，就带上Authorization
        # 为什么要带token？因为带上它请求额度更高，否则限流低不适合定时采集
        if settings.github_token:
            self.headers["Authorization"] = f"Bearer {settings.github_token}"

    def get_repository(self, owner: str, repo: str) -> dict:
        """
        获取某个 GitHub 仓库的基础信息。

        参数示例：
        owner = "openai"
        repo = "openai-python"

        对应 GitHub API：
        GET /repos/{owner}/{repo}

        返回数据里会包含：
        - full_name
        - description
        - html_url
        - stargazers_count
        - forks_count
        - open_issues_count
        - language
        - topics
        - archived
        - disabled
        - created_at
        - updated_at
        - pushed_at

        后面新增仓库接口会把这些字段写入 repositories 表。
        """
        # 拼出完整的url
        url = f"{self.base_url}/repos/{owner}/{repo}"
        # 使用httpx.Client发起请求,with会在请求后自动关闭连接资源
        with httpx.Client(timeout=20) as client:
            response = client.get(url, headers=self.headers)

        # 抛出异常
        # 404 仓库不存在
        # 401 token 无效
        # 403 被限流或没权限
        # 500 GitHub 服务异常
        response.raise_for_status()

        return response.json()

    def get_languages(self, owner: str, repo: str) -> dict:
        """
        获取仓库的语言占比。

        对应 GitHub API：
        GET /repos/{owner}/{repo}/languages

        返回示例：
        {
            "Python": 98.13,
            "JavaScript": 1.87
        }
        """
        url = f"{self.base_url}/repos/{owner}/{repo}/languages"
        with httpx.Client(timeout=20) as client:
            response = client.get(url, headers=self.headers)

        response.raise_for_status()
        # GitHub原始返回值：语言->字节数
        raw_languages: dict[str,int] = response.json()
        if not raw_languages:
            return {}

        total_bytes = sum(raw_languages.values())
        if total_bytes <= 0:
            return {}

        return {
            language: round((byte_count / total_bytes) * 100, 2) for language, byte_count in raw_languages.items()
        }

    def get_readme(self, owner: str, repo: str) -> dict | None:
        """
        获取仓库 README 信息。

        对应 GitHub API：
        GET /repos/{owner}/{repo}/readme

        为什么返回 dict | None？
        因为不是所有仓库都有 README。

        如果仓库没有 README，GitHub 会返回 404。
        这种情况不是系统错误，所以我们返回 None，
        让上层代码知道“这个仓库没有 README”。
        """
        url = f"{self.base_url}/repos/{owner}/{repo}/readme"
        with httpx.Client(timeout=20) as client:
            response = client.get(url, headers=self.headers)

        if response.status_code == 404:
            return None

        response.raise_for_status()
        return response.json()

    def get_rate_limit(self) -> dict:
        """
        查询 GitHub API 限流状态。

        对应 GitHub API：
        GET /rate_limit

        这个接口可以告诉我们：
        - 每小时最多能请求多少次
        - 已经用了多少次
        - 还剩多少次
        - 什么时候重置额度

        后面做定时采集时，这个信息很重要。
        如果剩余额度太低，就应该暂停或延迟采集。
        """
        url = f"{self.base_url}/rate_limit"

        with httpx.Client(timeout=20) as client:
            response = client.get(url, headers=self.headers)

        response.raise_for_status()
        return response.json()
