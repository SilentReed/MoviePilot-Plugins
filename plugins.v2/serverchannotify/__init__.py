from app.plugins import _PluginBase
from app.core.event import eventmanager, Event
from app.schemas.types import EventType, ChainEventType, NotificationType
from app.helper.service import ServiceInfo, ServiceConfigHelper, ServiceBaseHelper, NotificationHelper
import re
from serverchan_sdk import sc_send
from typing import Optional, Dict, Any, List, Tuple
from app.core.config import settings
from app.log import logger


class ServerChanNotify(_PluginBase):
    # 插件基本信息
    plugin_name = "Server酱³通知插件"
    plugin_desc = "实现 Server 酱消息通知功能，适配多种 MoviePilot 通知事件"
    plugin_icon = "https://github.com/SilentReed/MoviePilot-Plugins/main/icons/serverchan.png"
    plugin_version = "1.0"
    plugin_author = "SilentReed"
    author_url = "https://github.com/SilentReed"
    plugin_config_prefix = "SilentReed_serverchan_"
    plugin_order = 1
    auth_level = 1

    # Server 酱配置属性
    _server_jiang_uid = ""
    _server_jiang_sendkey = ""
    _enable_notify_types = []
    _notification_helper: NotificationHelper = None
    _send_test = False

    def init_plugin(self, config: dict = None):
        logger.info(f"Initializing plugin with config: {config}")
        if hasattr(settings, 'VERSION_FLAG'):
            version = settings.VERSION_FLAG  # V2
        else:
            version = "v1"

        if version == "v2":
            self.setup_v2()
        else:
            self.setup_v1()

        if config:
            self._server_jiang_sendkey = config.get("server_jiang_sendkey", "")
            self._enable_notify_types = config.get("enable_notify_types", [])
            self._send_test = config.get("send_test", False)

            # 若 uid 未提供，尝试从 sendkey 中提取
            if not self._server_jiang_uid and self._server_jiang_sendkey:
                match = re.search(r'^sctp(\d+)t', self._server_jiang_sendkey)
                if match:
                    self._server_jiang_uid = match.group(1)

            if self._send_test:
                flag = self.send_server_jiang_notification(
                    title="Server酱³通知插件测试",
                    desp="这是一条测试消息，用于验证 Server酱³通知插件是否正常工作。"
                )
                if flag:
                    self.systemmessage.put("Server酱³通知插件测试消息发送成功！")
                else:
                    self.systemmessage.put("Server酱³通知插件测试消息发送失败，请检查配置。")
                self._send_test = False
                self.__update_config()

    def setup_v2(self):
        self._notification_helper = NotificationHelper()
        logger.info("Setup for V2 version completed.")

    def setup_v1(self):
        logger.info("Setup for V1 version completed.")

    def __update_config(self):
        """
        更新配置
        """
        config = {
            "server_jiang_sendkey": self._server_jiang_sendkey,
            "enable_notify_types": self._enable_notify_types,
            "send_test": self._send_test
        }
        self.update_config(config)
        logger.info(f"Plugin configuration updated: {config}")

    def get_state(self) -> bool:
        state = bool(self._server_jiang_sendkey)
        logger.info(f"Plugin state: {state}")
        return state

    def _generate_notify_type_options(self):
        """
        生成通知类型选项列表
        """
        return [
            {
                "title": event_type.value,
                "value": event_type.name
            } for event_type in list(EventType) + list(ChainEventType) if event_type
        ]

    def get_form(self) -> tuple[list[dict], dict[str, Any]]:
        """
        拼装插件配置页面
        """
        # 生成通知类型选项
        notify_type_options = self._generate_notify_type_options()

        elements = [
            {
                'component': 'VForm',
                'content': [
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'server_jiang_sendkey',
                                            'label': 'Server 酱 SendKey',
                                            'hint': '从 SendKey 页面获取',
                                            'rules': [
                                                lambda value: bool(value) or 'SendKey 不能为空'
                                            ]
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'send_test',
                                            'label': '立刻发送测试',
                                            'hint': '开启后将发送一条测试消息，发送完成后自动关闭',
                                            'persistent-hint': True
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12
                                },
                                'content': [
                                    {
                                        'component': 'VSelect',
                                        'props': {
                                            'model': 'enable_notify_types',
                                            'label': '消息类型',
                                            'multiple': True,
                                            'chips': True,
                                            'clearable': True,
                                            'items': notify_type_options,
                                            'hint': '选择哪些类型的消息需要通过此渠道发送，缺省时不限制类型。'
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]

        config_suggest = {
            "server_jiang_sendkey": "",
            "enable_notify_types": [],
            "send_test": False
        }

        return elements, config_suggest

    def send_server_jiang_notification(self, title: str, desp: str = "", tags: str = ""):
        """
        发送 Server 酱通知
        """
        logger.info(f"Sending ServerChan notification: title={title}, desp={desp}, tags={tags}")
        if not self._server_jiang_sendkey:
            logger.error("ServerChan SendKey is not set.")
            return False

        options = {}
        if tags:
            options["tags"] = tags

        try:
            response = sc_send(self._server_jiang_sendkey, title, desp, options)
            logger.info(f"ServerChan SDK response: {response}")
            if response.get("errno") == 0:
                return True
            else:
                logger.error(f"Server 酱通知发送失败，错误信息: {response.get('errmsg')}")
        except Exception as e:
            logger.error(f"Server 酱通知发送出错: {e}")
        return False

    def handle_notification_event(self, event: Event):
        """
        处理通知事件
        """
        event_data = event.event_data
        event_type = event.event_type
        logger.info(f"Handling notification event: {event_type.name}, data={event_data}")
        if self._enable_notify_types and event_type.name not in self._enable_notify_types:
            logger.info(f"Event type {event_type.name} is not enabled for notification.")
            return

        if event_type == EventType.NoticeMessage:
            title = event_data.get("title")
            text = event_data.get("text")
        else:
            title = f"{event_type.value} 事件触发"
            text = str(event_data)

        if title or text:
            self.send_server_jiang_notification(title=title or text, desp=text)

    @eventmanager.register(list(EventType) + list(ChainEventType))
    def on_notification_events(self, event: Event):
        """
        监听所有通知事件，发送 Server 酱通知
        """
        self.handle_notification_event(event)