"""
运行时配置服务。

职责：
1. seed_default_configs()：首次启动把默认配置写入 app_configs 表（已有记录不覆盖）。
2. load_into_settings()：服务启动时把数据库里的配置合并进 settings 单例，覆盖 .env 的同名默认值。
3. list_configs()：返回分组配置给管理页面，敏感字段脱敏。
4. update_configs()：批量更新配置，先整体校验，全部合法才提交。
5. apply()：更新后把数据库配置重新合并进 settings 单例，并热重载调度器。
6. test_email() / test_llm()：连通性测试，改完配置立刻验证。

热生效原理：
- settings 是模块级可变单例，所有业务 service 都是"使用时实时读取 settings"，
  所以 setattr(settings, "smtp_host", "新值") 之后，下一次邮件发送/LLM 调用就会用新值。
- cron 变更走 scheduler_service.reload()，APScheduler 会按新规则重新注册任务。
- 唯一需要重启的配置是 DATABASE_URL、API_AUTH_TOKEN 等启动引导配置，它们不在页面提供修改入口。
"""
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from app.core.config import settings, DEFAULT_CONFIGS
from app.db.models import AppConfig
from app.services.email_digest_service import EmailDigestService
from app.services.scheduler_service import scheduler_service


def normalize_value(value_type: str, raw: str) -> str:
    """把页面传来的字符串按类型规范化之后存库"""
    if value_type == 'bool':
        # 布尔值统一存 "true"/"false"，避免页面传来 on/1/yes 等变体。
        return "true" if str(raw).strip().lower() in ("true","1","yes","on") else "false"
    if value_type == "int":
        # 整数：先转 int 校验合法性，再存回字符串。
        return str(int(str(raw).strip()))
    if value_type == "float":
        # 浮点数：同样先校验再存字符串。
        return str(float(str(raw).strip()))
    return str(raw).strip()  # 其他类型原样去掉首尾空白。


def to_python(value_type: str, value: str | None):
    """把数据库字符串转成 Python 类型，用于 setattr settings。"""
    if value is None:  # 数据库没存值时返回 None。
        return None
    if value_type == "bool":  # 布尔字符串转 bool。
        return value.strip().lower() in ("true", "1", "yes", "on")
    if value_type == "int":  # 整数字符串转 int。
        return int(value)
    if value_type == "float":  # 浮点字符串转 float。
        return float(value)
    return value  # 其他类型原样返回字符串。


def mask_secret(value: str | None) -> str:
    """敏感值脱敏，例如 sk-2e37****c1416f。"""
    if not value:  # 空值直接返回空字符串。
        return ""
    if len(value) <= 4:  # 太短的值整体打码。
        return "****"
    return f"{value[:2]}****{value[-4:]}"  # 保留首 2 位和末 4 位，中间打码。

class ConfigService:
    """管理 app_configs 表中的运行时配置。"""
    def __init__(self, db):
        self.db = db

    def seed_default_configs(self) -> int:
        """把 DEFAULT_CONFIGS 写入 app_configs 表，已有记录不覆盖。"""
        created = 0  # 统计本次新增数量。
        for key, category, value_type, is_secret, description, getter in DEFAULT_CONFIGS:  # 遍历默认清单。
            if self.db.get(AppConfig, key) is not None:  # 如果数据库已经有这条配置。
                continue  # 不覆盖管理员已经修改过的值。
            raw = getter(settings)  # 从 settings 读取 .env 的默认值。
            self.db.add(AppConfig(  # 创建新配置记录。
                key=key,  # 配置名。
                value=normalize_value(value_type, "" if raw is None else str(raw)),  # 规范化存储。
                category=category,  # 分组。
                value_type=value_type,  # 类型。
                is_secret=is_secret,  # 是否敏感。
                description=description,  # 中文说明。
            ))  # AppConfig 构造结束。
            created += 1  # 新增数量加一。
        if created:  # 如果确实新增了记录。
            self.db.commit()  # 提交写入。
        return created  # 返回新增数量，供启动日志使用。


    def load_into_settings(self) -> dict:
        """把 app_configs 里的配置 setattr 到 settings 单例，覆盖 .env 默认值。"""
        applied = 0  # 成功覆盖数量。
        failed = 0  # 转换失败数量。
        configs = self.db.query(AppConfig).all()  # 查询全部配置。
        for cfg in configs:  # 遍历配置。
            attr_name = cfg.key.lower()  # 配置 key 小写就是 settings 属性名。
            if not hasattr(settings, attr_name):  # 如果 settings 里没有这个属性。
                continue  # 跳过未知配置，避免启动失败。
            try:  # 类型转换可能失败。
                setattr(settings, attr_name, to_python(cfg.value_type, cfg.value))  # 更新 settings 单例。
                applied += 1  # 成功数量加一。
            except (ValueError, TypeError):  # 数据库里存了非法值。
                failed += 1  # 失败数量加一，不影响其他配置加载。
        return {"applied": applied, "failed": failed}  # 返回统计结果，供启动日志使用。

    def list_configs(self) -> dict:  # 返回分组配置和系统只读信息。
        """管理页面数据源：分组配置（敏感字段脱敏）+ 系统只读信息。"""
        self.seed_default_configs()  # 确保默认配置存在，首次查询时自动初始化。
        configs = self.db.query(AppConfig).order_by(AppConfig.category.asc(), AppConfig.key.asc()).all()  # 按分组、key 排序。
        groups: dict[str, list[dict]] = {}  # 分组结果。
        for cfg in configs:  # 遍历配置。
            if cfg.is_secret:  # 敏感字段。
                shown_value = mask_secret(cfg.value)  # 只回显脱敏值。
            else:  # 非敏感字段。
                shown_value = cfg.value or ""  # 回显完整值。
            groups.setdefault(cfg.category, []).append({  # 追加到对应分组。
                "key": cfg.key,  # 配置名。
                "value": shown_value,  # 回显值（敏感字段已脱敏）。
                "category": cfg.category,  # 分组。
                "value_type": cfg.value_type,  # 类型，页面决定渲染控件。
                "is_secret": cfg.is_secret,  # 是否敏感。
                "description": cfg.description or "",  # 中文说明。
            })  # 追加结束。
        return {  # 返回完整数据。
            "groups": groups,  # 分组配置。
            "system": {  # 系统只读信息。
                "app_name": settings.app_name,  # 服务名。
                "app_version": settings.app_version,  # 版本。
                "app_env": settings.app_env,  # 环境。
                "debug": settings.debug,  # 调试开关。
                "timezone": settings.timezone,  # 时区。
                "log_level": settings.log_level,  # 日志级别。
                "database_url": self._mask_database_url(settings.database_url),  # 数据库地址（脱敏）。
            },  # 系统信息结束。
        }  # 返回结束。

    def update_configs(self, updates: dict[str, str]) -> dict:  # 批量更新配置。
        """批量更新；先整体校验，全部合法才提交，避免部分生效。"""
        pending: list[tuple] = []  # 待写入的更新项。
        errors: dict[str, str] = {}  # 校验失败项。
        for key, raw_value in updates.items():  # 遍历页面传来的更新。
            meta = self._find_meta(key)  # 在默认清单里查找配置元信息。
            if meta is None:  # 如果是不认识的配置名。
                errors[key] = "未知配置项"  # 记录错误。
                continue  # 跳过。
            _, category, value_type, is_secret, description, _ = meta  # 解包元信息。
            if is_secret and (raw_value is None or str(raw_value).strip() == ""):  # 敏感字段留空。
                continue  # 表示"不修改"，直接跳过。
            try:  # 类型校验可能失败。
                normalized = normalize_value(value_type, raw_value)  # 规范化新值。
            except (ValueError, TypeError) as exc:  # 值不合法。
                errors[key] = f"值不合法: {exc}"  # 记录具体原因。
                continue  # 跳过该项。
            pending.append((key, category, value_type, is_secret, description, normalized))  # 收集合法更新项。
        if errors:  # 只要有任一字段失败。
            self.db.rollback()  # 整体回滚，不保存任何字段，保证一致性。
            return {"updated": [], "errors": errors}  # 返回错误，路由层返回 400。
        updated: list[str] = []  # 成功更新的 key 列表。
        for key, category, value_type, is_secret, description, normalized in pending:  # 遍历合法更新项。
            cfg = self.db.get(AppConfig, key)  # 查询已有记录。
            if cfg is None:  # 如果记录不存在。
                cfg = AppConfig(key=key)  # 创建新记录。
                self.db.add(cfg)  # 加入会话。
            cfg.value = normalized  # 写入新值。
            cfg.category = category  # 同步分组。
            cfg.value_type = value_type  # 同步类型。
            cfg.is_secret = is_secret  # 同步敏感标记。
            cfg.description = description  # 同步说明。
            updated.append(key)  # 记录更新成功的 key。
        self.db.commit()  # 全部合法，一次性提交。
        return {"updated": updated, "errors": errors}  # 返回结果。

    def apply(self) -> dict:  # 让数据库配置立即生效。
        """把数据库配置重新合并进 settings 单例，并热重载调度器。"""
        load_result = self.load_into_settings()  # 更新 settings 单例。
        scheduler_result = scheduler_service.reload()  # 热重载 APScheduler（cron 变更立即生效）。
        return {"load": load_result, "scheduler": scheduler_result}  # 返回生效结果。

    def test_email(self, to_email: str) -> dict:  # 测试 SMTP 配置。
        """用当前生效的 SMTP 配置发一封测试邮件。"""
        if not settings.smtp_host:  # 没配置服务器地址。
            return {"ok": False, "message": "SMTP_HOST 未配置"}  # 直接返回失败原因。
        if not settings.smtp_username or not settings.smtp_password:  # 缺用户名或密码。
            return {"ok": False, "message": "SMTP_USERNAME 或 SMTP_PASSWORD 未配置"}  # 返回失败原因。
        subject = f"【配置测试】{settings.app_name} SMTP 测试邮件"  # 测试邮件标题。
        now_text = datetime.now(ZoneInfo(settings.timezone)).strftime("%Y-%m-%d %H:%M:%S")  # 用配置时区格式化当前时间。
        text_content = f"这是一封来自配置管理页面的测试邮件，收到说明 SMTP 配置可用。\n发送时间: {now_text}"  # 纯文本内容。
        html_content = (  # HTML 内容。
            "<html><body>"
            "<p>这是一封来自配置管理页面的测试邮件，收到说明 SMTP 配置可用。</p>"
            f"<p>发送时间: {now_text}</p>"
            "</body></html>"
        )  # HTML 内容结束。
        try:  # 发送可能失败。
            EmailDigestService(self.db)._send_email(to_email, subject, text_content, html_content)  # 复用日报的发送方法。
            return {"ok": True, "message": "发送成功", "to_email": to_email}  # 返回成功。
        except Exception as exc:  # 捕获发送异常。
            return {"ok": False, "message": f"发送失败: {exc}"}  # 返回失败原因。

    def test_llm(self) -> dict:  # 测试 LLM 配置。
        """用当前生效的 LLM 配置调用一次最小 chat 请求，验证 Key/模型名/地址。"""
        if not settings.llm_enabled:  # 大模型总开关关闭。
            return {"ok": False, "message": "LLM_ENABLED=false，未启用大模型"}  # 返回失败原因。
        if not settings.llm_api_key:  # 没配 Key。
            return {"ok": False, "message": "LLM_API_KEY 未配置"}  # 返回失败原因。
        url = f"{settings.llm_api_base_url.rstrip('/')}/chat/completions"  # OpenAI-compatible 接口地址。
        headers = {  # 请求头。
            "Authorization": f"Bearer {settings.llm_api_key}",  # Bearer Token 鉴权。
            "Content-Type": "application/json",  # JSON 请求体。
        }  # 请求头结束。
        payload = {  # 最小请求体。
            "model": settings.llm_model,  # 当前模型名。
            "messages": [{"role": "user", "content": "只回复 ok"}],  # 最小对话。
            "max_tokens": 10,  # 限制输出长度，测试请求尽量小。
            "temperature": 0,  # 温度 0，输出稳定。
        }  # 请求体结束。
        start = time.monotonic()  # 记录请求开始时间。
        try:  # 网络请求可能失败。
            with httpx.Client(timeout=settings.llm_timeout_seconds) as client:  # 同步客户端，超时用配置值。
                response = client.post(url, headers=headers, json=payload)  # 发起请求。
            elapsed = round(time.monotonic() - start, 2)  # 计算耗时（秒）。
            if response.status_code == 200:  # 请求成功。
                data = response.json()  # 解析响应。
                choices = data.get("choices") or []  # 读取 choices。
                content = ""  # 模型回复。
                if choices:  # 有候选结果。
                    content = (choices[0].get("message") or {}).get("content") or ""  # 提取回复内容。
                return {  # 返回成功详情。
                    "ok": True,  # 成功标记。
                    "model": settings.llm_model,  # 当前模型名。
                    "elapsed_seconds": elapsed,  # 请求耗时。
                    "reply": content.strip()[:100],  # 回复内容截断展示。
                }  # 成功详情结束。
            return {  # HTTP 非 200。
                "ok": False,  # 失败标记。
                "model": settings.llm_model,  # 当前模型名。
                "status_code": response.status_code,  # 状态码，401=Key 错，404=地址或模型名错。
                "message": response.text[:200],  # 服务端错误信息截断。
            }  # 失败详情结束。
        except Exception as exc:  # 网络/超时等异常。
            return {"ok": False, "model": settings.llm_model, "message": str(exc)[:200]}  # 返回异常信息。

    def _find_meta(self, key: str):  # 在默认清单里查找配置元信息。
        """按 key 查找 DEFAULT_CONFIGS 里的元信息，找不到返回 None。"""
        for item in DEFAULT_CONFIGS:  # 遍历默认清单。
            if item[0] == key:  # key 匹配。
                return item  # 返回整条元信息。
        return None  # 找不到返回 None。

    def _mask_database_url(self, url: str) -> str:  # 数据库连接串脱敏。
        """只保留协议和主机部分，隐藏用户名密码。"""
        try:  # 解析可能失败。
            head, rest = url.split("://", 1)  # 拆分协议和剩余部分。
            host_part = rest.split("/", 1)[0]  # 取主机:端口部分。
            return f"{head}://***@{host_part}"  # 用户名密码统一打码。
        except ValueError:  # 不是标准连接串。
            return "***"  # 整体打码。

