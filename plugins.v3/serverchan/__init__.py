import re
from typing import Any

from app.sdk.events import Event, eventmanager
from app.sdk.logging import logger
from app.sdk.network import AsyncRequestUtils
from app.plugins import _PluginBase
from app.schemas.types import EventType, NotificationType


class ServerChan(_PluginBase):
    """通过 Server酱³ 发送消息通知，支持 APP 推送。"""

    # 插件名称
    plugin_name = "Server酱³通知"
    # 插件描述
    plugin_desc = "通过 Server酱³ 发送消息通知，支持 APP 推送"
    # 插件图标
    plugin_icon = "icons/serverchan.png"
    # 插件版本
    plugin_version = "2.1.1"
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
    _tags: str = ""
    _msgtypes: list[str] = []

    def init_plugin(self, config: dict | None = None) -> None:
        """读取配置并建立本次运行所需状态。"""
        config = config or {}
        self._enabled = bool(config.get("enabled"))
        self._onlyonce = bool(config.get("onlyonce"))
        self._sendkey = config.get("sendkey")
        self._tags = config.get("tags") or ""
        self._msgtypes = config.get("msgtypes") or []

        # 自动从 SendKey 提取 UID
        self._uid = self._extract_uid(self._sendkey)

        if self._onlyonce:
            import threading
            threading.Thread(
                target=self._thread_send_message,
                args=("Server酱³通知测试", "插件已启用"),
                daemon=True,
            ).start()
            self._onlyonce = False
            self._save_config()

    @staticmethod
    def _extract_uid(sendkey: str | None) -> str | None:
        """从 SendKey 中自动提取 UID。

        Server酱³ SendKey 格式: sctp{UID}t{rest}
        例如: sctp123456txxxxxxxxxxxxx → UID = 123456
        """
        if not sendkey:
            return None
        match = re.match(r"^sctp(\d+)t", sendkey)
        if match:
            return match.group(1)
        return None

    def get_state(self) -> bool:
        """返回插件当前是否启用。"""
        if not self._enabled:
            return False
        if not self._uid or not self._sendkey:
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
            "tags": "",
            "msgtypes": [],
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
                                            "placeholder": "sctp123456txxxxxxxxxxxxx",
                                            "hint": "在 Server酱³ 官网获取，UID 会自动从 SendKey 提取",
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
            "tags": self._tags,
            "msgtypes": self._msgtypes,
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
            logger.error(f"Server酱³ 测试消息发送失败: {e}")

    def _validate_config(self) -> str | None:
        """校验必要配置项，返回错误信息或 None。"""
        if not self._sendkey:
            return "请填写 SendKey"
        if not self._uid:
            return f"无法从 SendKey 提取 UID，请检查格式（应为 sctp{{数字}}t...）"
        if not self._sendkey.startswith("sctp"):
            return "SendKey 格式不正确，应以 sctp 开头"
        return None

    def _build_send_url(self) -> str:
        """构建发送 URL。"""
        return f"https://{self._uid}.push.ft07.com/send/{self._sendkey}.send"

    @staticmethod
    def _build_message_data(
        title: str, text: str, image: str | None = None, tags: str = ""
    ) -> dict[str, str]:
        """构建消息数据，支持图片和标签。"""
        data: dict[str, str] = {
            "title": title,
            "desp": f"{title}\n\n{text}",
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

            logger.info(f"Server酱³ 发送消息: {title}")
            res = await AsyncRequestUtils(timeout=self.REQUEST_TIMEOUT).post_res(
                url=url, data=data
            )

            return self._handle_response(res, title)

        except ConnectionError as e:
            logger.error(f"Server酱³ 连接错误: {e}")
            return False, f"连接错误: {e}"
        except TimeoutError as e:
            logger.error(f"Server酱³ 请求超时: {e}")
            return False, f"请求超时: {e}"
        except ValueError as e:
            logger.error(f"Server酱³ 数据解析错误: {e}")
            return False, f"数据解析错误: {e}"
        except Exception as e:
            logger.error(f"Server酱³ 消息发送异常: {e}")
            return False, f"发送异常: {e}"

    def _handle_response(self, res: Any, title: str) -> tuple[bool, str]:
        """处理 HTTP 响应。"""
        if not res:
            logger.warning("Server酱³ 请求失败，无响应")
            return False, "请求失败，无响应"

        if res.status_code != 200:
            logger.warning(f"Server酱³ 请求失败，状态码: {res.status_code}")
            if res.text:
                logger.warning(f"响应内容: {res.text[:self.MAX_LOG_LENGTH]}")
            return False, f"请求失败，状态码: {res.status_code}"

        try:
            result = res.json()
            if result.get("code") == 0:
                logger.info(f"Server酱³ 消息发送成功: {title}")
                return True, "发送成功"
            else:
                error_msg = result.get("message", "未知错误")
                logger.warning(f"Server酱³ 消息发送失败: {error_msg}")
                return False, error_msg
        except ValueError as e:
            logger.error(f"Server酱³ 响应解析失败: {e}")
            return False, f"响应解析失败: {e}"

    # ---- 消息类型过滤 ----

    def _should_send_message(self, msg_body: dict) -> bool:
        """判断是否应发送该类型的消息。"""
        msg_type = msg_body.get("type")
        if not msg_type or not self._msgtypes:
            return True

        if isinstance(msg_type, NotificationType):
            if msg_type.name not in self._msgtypes:
                logger.debug(f"Server酱³ 消息类型 {msg_type.value} 未开启，跳过")
                return False
        elif isinstance(msg_type, str):
            if msg_type not in self._msgtypes:
                logger.debug(f"Server酱³ 消息类型 {msg_type} 未开启，跳过")
                return False

        return True

    # ---- 事件处理 ----

    @eventmanager.register(EventType.NoticeMessage)
    async def send(self, event: Event) -> None:
        """处理通知消息事件。"""
        if not self.get_state():
            logger.debug("Server酱³ 插件未启用或参数未配置")
            return

        if not event.event_data:
            logger.debug("Server酱³ 事件数据为空")
            return

        msg_body = event.event_data

        # 提取消息字段
        title = msg_body.get("title")
        text = msg_body.get("text")
        image = msg_body.get("image")

        if not title and not text:
            logger.warning("Server酱³ 标题和内容不能同时为空")
            return

        # 消息类型过滤
        if not self._should_send_message(msg_body):
            return

        logger.info(f"Server酱³ 收到消息: {title}")
        if image:
            logger.info(f"Server酱³ 附带图片: {image}")

        result = await self._async_send_message(title, text, image)
        if result:
            success, msg = result
            if not success:
                logger.warning(f"Server酱³ 发送失败: {msg}")
