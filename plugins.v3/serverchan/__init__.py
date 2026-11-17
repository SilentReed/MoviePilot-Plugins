import re
from typing import Any

from app.sdk.events import Event, eventmanager
from app.sdk.logging import logger
from app.sdk.network import AsyncRequestUtils
from app.plugins import _PluginBase
from app.schemas.types import EventType, NotificationType


class ServerChan(_PluginBase):
    """通过 Server酱 发送消息通知，同时支持 SCMax 与 Server酱³ 两种 SendKey。"""

    # 插件名称
    plugin_name = "Server酱³通知"
    # 插件描述
    plugin_desc = "通过 Server酱（SCMax / Server酱³）发送消息通知，支持 APP 推送"
    # 插件图标
    plugin_icon = "icons/serverchan.png"
    # 插件版本
    plugin_version = "2.3.1"
    # 插件作者
    plugin_author = "SilentReed"
    # 作者主页
    author_url = "https://github.com/SilentReed"
    # 插件配置项 ID 前缀
    plugin_config_prefix = "serverchan_"
    # 加载顺序
    plugin_order = 27
    # 可使用的用户级别
    auth_level = 1

    # 常量定义
    REQUEST_TIMEOUT = 10
    MAX_LOG_LENGTH = 200

    # 私有属性
    _enabled: bool = False
    _onlyonce: bool = False
    _uid: str | None = None
    _sendkey: str | None = None
    _api_base: str = ""
    _tags: str = ""
    _msgtypes: list[str] = []
    _layout: bool = True

    # SendKey 格式：SCMax 为 scx-{UID}-{TOKEN}，Server酱³ 为 sctp{UID}t{TOKEN}
    SCMAX_KEY_RE = re.compile(r"^scx-(\d+)-")
    SCT_KEY_RE = re.compile(r"^sctp(\d+)t")
    # 留空时按 SendKey 前缀自动选择接口域名
    SCMAX_BASE = "https://{uid}.max.ft07.com"
    SCT_BASE = "https://{uid}.push.ft07.com"
    # 形如 `1. 名称 | 状态：启用 | Cookie：已配置` 的条目行
    ITEM_LINE_RE = re.compile(r"^\s*(\d+)[.、]\s*(.+?)\s*$")

    def init_plugin(self, config: dict | None = None) -> None:
        """读取配置并建立本次运行所需状态。"""
        config = config or {}
        self._enabled = bool(config.get("enabled"))
        self._onlyonce = bool(config.get("onlyonce"))
        self._sendkey = (config.get("sendkey") or "").strip() or None
        self._api_base = (config.get("api_base") or "").strip()
        self._tags = config.get("tags") or ""
        self._msgtypes = config.get("msgtypes") or []
        # 旧配置没有该字段时默认开启排版优化
        layout = config.get("layout")
        self._layout = True if layout is None else bool(layout)

        # 自动从 SendKey 提取 UID
        self._uid = self._extract_uid(self._sendkey)

        if self._onlyonce:
            import threading
            threading.Thread(
                target=self._thread_send_message,
                args=("Server酱通知测试", "插件已启用"),
                daemon=True,
            ).start()
            self._onlyonce = False
            self._save_config()

    @classmethod
    def _extract_uid(cls, sendkey: str | None) -> str | None:
        """从 SendKey 中自动提取 UID。

        支持两种格式：
        - SCMax: scx-{UID}-{TOKEN}，例如 scx-10325-xxxx → UID = 10325
        - Server酱³: sctp{UID}t{TOKEN}，例如 sctp123456txxxx → UID = 123456
        """
        if not sendkey:
            return None
        sendkey = sendkey.strip()
        match = cls.SCMAX_KEY_RE.match(sendkey) or cls.SCT_KEY_RE.match(sendkey)
        if match:
            return match.group(1)
        return None

    def get_state(self) -> bool:
        """返回插件当前是否启用。"""
        if not self._enabled:
            return False
        if not self._sendkey:
            return False
        # SCMax（scx- 开头）必须显式填写专属推送地址
        if self._sendkey.startswith("scx-") and not self._api_base:
            return False
        # 其余情况未指定接口地址时，必须能从 SendKey 解析出 UID
        if not self._api_base and not self._uid:
            return False
        return True

    @staticmethod
    def get_command() -> list[dict[str, Any]]:
        """当前插件不注册远程命令。"""
        return []

    def get_api(self) -> list[dict[str, Any]]:
        """当前插件不注册后端 API。"""
        return []

    def get_form(self) -> tuple[list[dict], dict[str, Any]]:
        """返回配置页面和默认配置。"""
        msg_type_options = self._build_message_type_options()
        return self._build_form_config(msg_type_options), {
            "enabled": False,
            "onlyonce": False,
            "sendkey": "",
            "api_base": "",
            "tags": "",
            "msgtypes": [],
            "layout": True,
        }

    def get_page(self) -> list[dict] | None:
        """返回插件详情页。"""
        status_text = "已启用" if self.get_state() else "未启用"
        status_color = "success" if self.get_state() else "warning"
        uid_display = self._uid or "未识别"
        sendkey_display = f"{self._sendkey[:10]}..." if self._sendkey and len(self._sendkey) > 10 else (self._sendkey or "未配置")

        return [
            {
                "component": "VCard",
                "props": {"variant": "tonal"},
                "content": [
                    {
                        "component": "VCardTitle",
                        "props": {"class": "text-h6"},
                        "text": "Server酱³通知 状态",
                    },
                    {
                        "component": "VCardText",
                        "content": [
                            {
                                "component": "VRow",
                                "content": [
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 6},
                                        "content": [
                                            {
                                                "component": "VAlert",
                                                "props": {
                                                    "type": status_color,
                                                    "variant": "tonal",
                                                    "text": f"状态: {status_text}",
                                                },
                                            },
                                        ],
                                    },
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 6},
                                        "content": [
                                            {
                                                "component": "VAlert",
                                                "props": {
                                                    "type": "info",
                                                    "variant": "tonal",
                                                    "text": f"UID: {uid_display}",
                                                },
                                            },
                                        ],
                                    },
                                ],
                            },
                            {
                                "component": "VRow",
                                "content": [
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 6},
                                        "content": [
                                            {
                                                "component": "VAlert",
                                                "props": {
                                                    "type": "info",
                                                    "variant": "tonal",
                                                    "text": f"SendKey: {sendkey_display}",
                                                },
                                            },
                                        ],
                                    },
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 6},
                                        "content": [
                                            {
                                                "component": "VAlert",
                                                "props": {
                                                    "type": "info",
                                                    "variant": "tonal",
                                                    "text": f"版本: v{self.plugin_version}",
                                                },
                                            },
                                        ],
                                    },
                                ],
                            },
                        ],
                    },
                ],
            }
        ]

    def stop_service(self) -> None:
        """释放插件创建的后台资源。"""
        self._enabled = False

    # ---- 消息类型选项 ----

    @staticmethod
    def _build_message_type_options() -> list[dict[str, str]]:
        """构建消息类型下拉选项。"""
        options = []
        for item in NotificationType:
            options.append({
                "title": item.value,
                "value": item.name,
            })
        return options

    # ---- 表单构建 ----

    @staticmethod
    def _build_form_config(msg_type_options: list[dict[str, str]]) -> list[dict]:
        """构建 Vuetify 配置表单。"""
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "enabled",
                                            "label": "启用插件",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "onlyonce",
                                            "label": "测试插件（立即运行）",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "sendkey",
                                            "label": "SendKey",
                                            "placeholder": "scx-10325-xxxxxxxxxxxxxxxx 或 sctp123456txxxxxxxx",
                                            "hint": "SCMax 的 SendKey 形如 scx-{UID}-{TOKEN}（需同时填写接口地址），Server酱³ 形如 sctp{UID}t{TOKEN}（接口地址可留空）",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "api_base",
                                            "label": "接口地址（使用 SCMax 时必填）",
                                            "placeholder": "https://10325.max.ft07.com",
                                            "hint": "使用 SCMax（SendKey 以 scx- 开头）时必填：请填写 SCMax 控制台给出的账户专属推送地址，形如 https://{你的UID}.max.ft07.com；使用 Server酱³（sctp 开头）时可留空，插件将自动走 https://{UID}.push.ft07.com。插件会向 {接口地址}/send/{SendKey} 发送",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "tags",
                                            "label": "标签",
                                            "placeholder": "MoviePilot|媒体",
                                            "hint": "标签列表，多个标签使用竖线(|)分隔",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "layout",
                                            "label": "正文排版优化",
                                            "hint": "去掉与标题重复的首行，把「1. 名称 | k：v | k：v」拆成两行要点，并补足换行，避免微信端把多行挤成一段",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VSelect",
                                        "props": {
                                            "multiple": True,
                                            "chips": True,
                                            "model": "msgtypes",
                                            "label": "消息类型（不选则接收所有）",
                                            "items": msg_type_options,
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                ],
            }
        ]

    # ---- 配置保存 ----

    def _save_config(self) -> bool:
        """保存插件当前配置。"""
        return self.update_config({
            "enabled": self._enabled,
            "onlyonce": self._onlyonce,
            "sendkey": self._sendkey,
            "api_base": self._api_base,
            "tags": self._tags,
            "msgtypes": self._msgtypes,
            "layout": self._layout,
        })

    # ---- 消息发送 ----

    def _thread_send_message(self, title: str, text: str) -> None:
        """在线程中同步调用异步发送方法。"""
        import asyncio
        try:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(self._async_send_message(title, text))
            loop.close()
        except Exception as e:
            logger.error(f"Server酱 测试消息发送失败: {e}")

    def _validate_config(self) -> str | None:
        """校验必要配置项，返回错误信息或 None。"""
        if not self._sendkey:
            return "请填写 SendKey"
        if self._sendkey.startswith("scx-") and not self._api_base:
            return (
                "使用 SCMax 的 SendKey（scx- 开头）时必须填写接口地址，"
                "请登录 SCMax 控制台复制账户专属推送地址，形如 https://{你的UID}.max.ft07.com"
            )
        if self._uid is None and not self._api_base:
            return (
                "无法从 SendKey 提取 UID，请检查格式："
                "SCMax 应为 scx-{UID}-{TOKEN}，Server酱³ 应为 sctp{UID}t{TOKEN}；"
                "如使用自建接口，请一并填写接口地址"
            )
        return None

    def _build_send_url(self) -> str:
        """构建发送 URL。

        优先使用显式配置的接口地址（SCMax 下为必填）：
        - SCMax: {接口地址}/send/{SendKey}，接口地址未填时兜底 https://{UID}.max.ft07.com
        - Server酱³: https://{UID}.push.ft07.com/send/{SendKey}.send
        """
        if self._api_base:
            base = self._api_base.rstrip("/")
            if base.endswith("/send"):
                return f"{base}/{self._sendkey}"
            return f"{base}/send/{self._sendkey}"
        if self._sendkey and self._sendkey.startswith("scx-"):
            return f"{self.SCMAX_BASE.format(uid=self._uid)}/send/{self._sendkey}"
        return f"{self.SCT_BASE.format(uid=self._uid)}/send/{self._sendkey}.send"

    @staticmethod
    def _format_text(title: str | None, text: str | None) -> str:
        """把任意上游文本整理成适合微信端渲染的 Markdown 正文（不改动文字内容）。

        通用规则，对全部通知生效：
        - 去掉与标题完全重复的首行，去掉首尾空行
        - 行内以 `|` 分隔的多字段（≥3 段且至少两段为 `键：值`）拆成两行：
          首段单独成行（带序号时加粗），其余各段用 ` · ` 连接
        - 每个非空行末尾补两个空格（Markdown 硬换行），修复微信端把多行挤成一段
        - 代码块、Markdown 表格行、标题/引用/列表/图片行原样保留，只补硬换行
        """
        if not text:
            return ""
        normalized = str(text).replace("\r\n", "\n").replace("\r", "\n")
        lines = [ln.rstrip() for ln in normalized.split("\n")]
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        if title and lines:
            head = lines[0].strip().strip("*#").strip()
            if head and head == str(title).strip():
                lines.pop(0)
                while lines and not lines[0].strip():
                    lines.pop(0)

        out: list[str] = []
        in_code = False
        for ln in lines:
            raw = ln.rstrip()
            stripped = raw.strip()
            if stripped.startswith("```"):
                in_code = not in_code
                out.append(raw)
                continue
            if in_code:
                out.append(raw)
                continue
            if not stripped:
                out.append("")
                continue
            # Markdown 表格行保持结构，不能被拆
            if stripped.startswith("|"):
                out.append(raw)
                continue
            # 行内多字段拆分：如 `1. 朱雀 | 状态：启用 | Cookie：已配置 | 域名：xxx`
            segments = [seg.strip() for seg in raw.split("|")]
            segments = [seg for seg in segments if seg]
            kv_like = sum(1 for seg in segments[1:] if "：" in seg or ": " in seg)
            if len(segments) >= 3 and kv_like >= 2:
                head_text = segments[0]
                if ServerChan.ITEM_LINE_RE.match(head_text):
                    head_text = f"**{head_text}**"
                out.append(head_text + "  ")
                out.append(" · ".join(segments[1:]) + "  ")
                continue
            # Markdown 结构行（标题/引用/列表/图片）只补硬换行
            out.append(raw + "  ")
        return "\n".join(out).strip()

    def _build_message_data(
        self, title: str, text: str, image: str | None = None, tags: str = ""
    ) -> dict[str, str]:
        """构建消息数据，支持图片、标签与排版优化。"""
        if text:
            desp = self._format_text(title, text) if self._layout else f"{title}\n\n{text}"
        else:
            desp = title or ""
        data: dict[str, str] = {
            "title": title,
            "desp": desp,
        }
        if tags:
            data["tags"] = tags
        if image:
            data["desp"] += f"\n\n![封面]({image})"
        return data

    async def _async_send_message(
        self, title: str, text: str, image: str | None = None
    ) -> tuple[bool, str]:
        """异步发送消息，支持图片和标签。"""
        try:
            error = self._validate_config()
            if error:
                logger.error(f"Server酱³: {error}")
                return False, error

            url = self._build_send_url()
            data = self._build_message_data(title, text, image, self._tags)

            logger.info(f"Server酱 发送消息: {title}")
            res = await AsyncRequestUtils(timeout=self.REQUEST_TIMEOUT).post_res(
                url=url, data=data
            )

            return self._handle_response(res, title)

        except ConnectionError as e:
            logger.error(f"Server酱 连接错误: {e}")
            return False, f"连接错误: {e}"
        except TimeoutError as e:
            logger.error(f"Server酱 请求超时: {e}")
            return False, f"请求超时: {e}"
        except ValueError as e:
            logger.error(f"Server酱 数据解析错误: {e}")
            return False, f"数据解析错误: {e}"
        except Exception as e:
            logger.error(f"Server酱 消息发送异常: {e}")
            return False, f"发送异常: {e}"

    def _handle_response(self, res: Any, title: str) -> tuple[bool, str]:
        """处理 HTTP 响应。"""
        if not res:
            logger.warning("Server酱 请求失败，无响应")
            return False, "请求失败，无响应"

        if res.status_code != 200:
            logger.warning(f"Server酱 请求失败，状态码: {res.status_code}")
            if res.text:
                logger.warning(f"响应内容: {res.text[:self.MAX_LOG_LENGTH]}")
            return False, f"请求失败，状态码: {res.status_code}"

        try:
            result = res.json()
            code = result.get("code", result.get("errno"))
            message = str(result.get("message") or "")
            if code == 0 or message.upper() == "SUCCESS":
                logger.info(f"Server酱 消息发送成功: {title}")
                return True, "发送成功"
            else:
                error_msg = result.get("error") or result.get("message") or "未知错误"
                logger.warning(f"Server酱 消息发送失败: {error_msg}")
                return False, error_msg
        except ValueError as e:
            # 接口返回非 JSON（如 "Invalid sendkey"）时，把原文带出来便于排错
            raw = (res.text or "").strip()[:self.MAX_LOG_LENGTH]
            logger.error(f"Server酱 响应解析失败: {e}, 原文: {raw}")
            return False, f"响应解析失败: {raw or e}"

    # ---- 消息类型过滤 ----

    def _should_send_message(self, msg_body: dict) -> bool:
        """判断是否应发送该类型的消息。"""
        msg_type = msg_body.get("type")
        if not msg_type or not self._msgtypes:
            return True

        if isinstance(msg_type, NotificationType):
            if msg_type.name not in self._msgtypes:
                logger.debug(f"Server酱 消息类型 {msg_type.value} 未开启，跳过")
                return False
        elif isinstance(msg_type, str):
            if msg_type not in self._msgtypes:
                logger.debug(f"Server酱 消息类型 {msg_type} 未开启，跳过")
                return False

        return True

    # ---- 事件处理 ----

    @eventmanager.register(EventType.NoticeMessage)
    async def send(self, event: Event) -> None:
        """处理通知消息事件。"""
        if not self.get_state():
            logger.debug("Server酱 插件未启用或参数未配置")
            return

        if not event.event_data:
            logger.debug("Server酱 事件数据为空")
            return

        msg_body = event.event_data

        # 提取消息字段
        title = msg_body.get("title")
        text = msg_body.get("text")
        image = msg_body.get("image")

        if not title and not text:
            logger.warning("Server酱 标题和内容不能同时为空")
            return

        # 消息类型过滤
        if not self._should_send_message(msg_body):
            return

        logger.info(f"Server酱 收到消息: {title}")
        if image:
            logger.info(f"Server酱 附带图片: {image}")

        result = await self._async_send_message(title, text, image)
        if result:
            success, msg = result
            if not success:
                logger.warning(f"Server酱 发送失败: {msg}")
