import json
import logging

from app.db.models import Repository
from app.services.llm_client import LLMClient

logger = logging.getLogger(__name__)

"""
把 GitHub README 或 description 整理成中文项目画像。
"""
class ChineseProfileService:
    def __init__(self):
        self.llm = LLMClient()

    def build_profile(self,repository, readme_text, fallback_text):
        source_text = self._prepare_source_text(readme_text, fallback_text)
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(repository, source_text)
        content = self.llm.chat_json(system_prompt, user_prompt)

        if not content:
            parsed = self._parse_profile_json(content)
            if parsed:
                return parsed

        return self._fallback_profile(repository,source_text)

    def _prepare_source_text(self, readme_text, fallback_text):
        raw_text = readme_text or fallback_text or ""  # 优先使用 README，缺失时使用 GitHub description。
        clean_text = " ".join(raw_text.split())
        return clean_text

    def _build_system_prompt(self):
        return (
            "你是一个面向中文技术读者的开源项目分析助手。"  # 定义模型角色。
            "你需要根据 GitHub README 或 description 生成客观、克制、可读的中文项目画像。"  # 定义输出目标。
            "不要编造输入文本中没有的信息。"  # 防止幻觉。
            "只输出 JSON，不要输出 Markdown，不要输出解释。"  # 降低 JSON 解析失败概率。
        )

    def _build_user_prompt(self, repository, source_text):
        return f"""请把下面 GitHub 项目信息整理成中文画像。

                仓库名称：{repository.full_name}
                主要语言：{repository.primary_language or "未知"}
                Stars：{repository.stars}
                Forks：{repository.forks}
                Open Issues：{repository.open_issues}
                GitHub 描述：{repository.description or "暂无"}
                
                README 或描述正文：
                {source_text}
                
                请严格返回下面 JSON 结构：
                {{
                  "summary": "80 字以内中文一句话简介",
                  "features": ["2-5 条中文功能点"],
                  "audience": ["1-3 条中文适用人群"],
                  "highlights": ["2-5 条中文亮点"],
                  "status": "complete"
                }}
            """

    def _parse_profile_json(self, content):
        """解析模型的返回"""
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse LLM profile JSON: %s", exc)

            return None  # 返回 None，让上层走兜底。
        summary = str(data.get("summary") or "").strip() # 提取summary并去掉空白
        features = self._normalize_list(data.get("features"))  # 提取 features，保证是字符串数组。
        audience = self._normalize_list(data.get("audience"))  # 提取 audience，保证是字符串数组。
        highlights = self._normalize_list(data.get("highlights"))  # 提取 highlights，保证是字符串数组。

        if not summary:
            return None

        return {
            "summary": summary[:120],  # 再做一次长度保护，避免模型输出过长。
            "features": features[:5] or ["项目提供了可复用的开源能力。"],  # 保证 features 至少有一条。
            "audience": audience[:3] or ["关注 AI 应用开发的技术读者。"],  # 保证 audience 至少有一条。
            "highlights": highlights[:5] or ["项目近期热度较高，值得关注。"],  # 保证 highlights 至少有一条。
            "status": "complete",  # 模型成功生成时标记 complete。
        }

    def _normalize_list(self, value):
        if isinstance(value, list):  # 如果模型按要求返回数组。
            return [str(item).strip() for item in value if str(item).strip()]  # 去掉空值并转成字符串。
        if isinstance(value, str) and value.strip():  # 如果模型误返回字符串。
            return [value.strip()]  # 包装成数组，避免类型不匹配。
        return []  # 其他情况返回空数组。

    def _fallback_profile(self, repository: Repository, source_text: str) -> dict:
        """本地兜底中文画像。"""
        summary_source = repository.description or source_text or repository.full_name  # 优先用 description 做兜底摘要来源。
        summary = self._fallback_summary(repository, summary_source)  # 生成中文兜底摘要。
        features = self._fallback_features(source_text)  # 根据关键词生成中文功能点。
        audience = self._fallback_audience(repository)  # 根据语言生成适用人群。
        highlights = self._fallback_highlights(repository)  # 根据 stars 和 tags 生成亮点。
        return {  # 返回与模型输出一致的结构。
            "summary": summary,  # 中文摘要。
            "features": features,  # 中文功能点。
            "audience": audience,  # 中文适用人群。
            "highlights": highlights,  # 中文亮点。
            "status": "partial",  # 兜底生成不是模型完整分析，所以标记 partial。
        }

    def _fallback_summary(self, repository: Repository, text: str) -> str:  # 生成兜底摘要。
        clean_text = " ".join(text.split())  # 压缩空白。
        if not clean_text:  # 如果没有任何可用描述。
            return f"{repository.full_name} 是一个近期热度较高的开源项目。"  # 返回最小可用中文简介。
        return f"{repository.full_name} 是一个与 AI/Agent 相关的开源项目，原始简介为：{clean_text[:80]}"  # 保留原始语义并转成中文说明。

    def _fallback_features(self, text: str) -> list[str]:  # 根据关键词生成兜底功能点。
        lowered = text.lower()  # 转小写便于关键词匹配。
        features: list[str] = []  # 保存功能点。
        if "agent" in lowered:  # 命中 agent。
            features.append("支持 AI Agent 或自动化工作流场景。")  # 添加中文功能点。
        if "rag" in lowered:  # 命中 rag。
            features.append("支持检索增强生成或知识库相关能力。")  # 添加中文功能点。
        if "workflow" in lowered:  # 命中 workflow。
            features.append("提供工作流编排或流程自动化能力。")  # 添加中文功能点。
        return features[:5] or ["提供可复用的开源项目能力。"]  # 没命中关键词时返回通用中文功能点。

    def _fallback_audience(self, repository: Repository) -> list[str]:  # 生成兜底适用人群。
        audience = ["关注 AI 应用和开源工具的技术读者。"]  # 默认适用人群。
        if repository.primary_language:  # 如果 GitHub 有主要语言。
            audience.append(f"{repository.primary_language} 开发者。")  # 增加语言开发者。
        return audience  # 返回适用人群。

    def _fallback_highlights(self, repository: Repository) -> list[str]:  # 生成兜底亮点。
        highlights = [f"项目当前拥有 {repository.stars} 个 GitHub Stars。"]  # stars 是最直接的热度指标。
        if repository.tags:  # 如果 discovery 阶段写入了标签。
            highlights.append(f"命中标签：{', '.join(repository.tags)}。")  # 用中文描述命中标签。
        return highlights  # 返回亮点列表。
