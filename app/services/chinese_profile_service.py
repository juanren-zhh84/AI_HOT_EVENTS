import json
import logging

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

        if content:  # LLM 成功返回内容时才尝试解析。
            parsed = self._parse_profile_json(content)
            if parsed:
                return parsed

        return None  # LLM 失败或解析失败：不生成兜底画像，由上层跳过该仓库。

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
        if not content:  # 防御：空内容直接走兜底，避免 json.loads(None) 抛 TypeError。
            return None
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
