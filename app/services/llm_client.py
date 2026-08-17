import logging

import httpx

logger = logging.getLogger(__name__)

from app.core.config import settings


class LLMClient:
    def __init__(self):
        self.enabled = settings.llm_enabled
        self.provider = settings.llm_provider
        self.base_url = settings.llm_api_base_url.rstrip("/") # 去掉末尾斜杠，避免拼接口地址时出现双斜杠。
        self.api_key = settings.llm_api_key
        self.model = settings.llm_model
        self.timeout = settings.llm_timeout_seconds
        self.temperature = settings.llm_temperature

    def chat_json(self,system_prompt, user_prompt):
        if not self.enabled:
            return None
        if not self.api_key:
            logger.warning("缺少api_key")
            return None

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role":"system","content":system_prompt},
                {"role":"user","content":user_prompt}, # user prompt 放项目 README、description 等内容。
            ],
            "temperature": self.temperature,
            "response_format":{"type":"json_object"},# 要求模型返回 JSON 对象，降低解析失败概率。
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            logger.warning("LLM获取失败：provider=%s model=%s status=%s", self.provider, self.model, exc.response.status_code) # 记录状态码，不记录 API Key。
            return None
        except httpx.HTTPError as exc:
            logger.warning("LLM获取错误：provider=%s model=%s error=%s", self.provider, self.model, exc) # 记录网络错误
            return None
        except ValueError as exc:
            logger.warning("LLM没有响应有效的JSON: provider=%s model=%s error=%s", self.provider, self.model, exc) # 解析失败
            return None

        choices = data.get("choices") or []  # 读取choices，兼容异常空响应
        if not choices:
            logger.warning("LLM没有返回候选结果: provider=%s model=%s", self.provider, self.model)
            return None

        message = choices[0].get("message") or {} # 读取第一个候选里的message
        content = message.get("content") or {}
        if not content:
            logger.warning("LLM生成的内容为空：: provider=%s model=%s", self.provider, self.model)
            return None
        return content
    

