from app.plugins import _PluginBase
from app.core.event import eventmanager, Event
from app.schemas.types import EventType, ChainEventType, NotificationType
from app.helper.service import ServiceInfo, ServiceConfigHelper, ServiceBaseHelper, NotificationHelper
import re
import requests

from urllib.parse import urlencode, quote
from typing import Optional, Dict, Any, List, Tuple
from app.core.config import settings


class ServerChanNotify(_PluginBase):
    # 插件基本信息
    plugin_name = "Server酱³通知插件"
    plugin_desc = "实现 Server 酱消息通知功能，适配多种 MoviePilot 通知事件"
    plugin_icon = "https://gh-proxy.com/github.com/SilentReed/MoviePilot-Plugins/raw/refs/heads/main/icons/serverchan.png"
    plugin_version = "1.0"
    plugin_author = "SilentReed"
    # 作者主页
    author_url = "https://github.com/SilentReed"
    plugin_config_prefix = "SilentReed_serverchan_"
    plugin_order = 1
    auth_level = 1

    # Server 酱配置属性
    _server_jiang_uid = ""
    _server_jiang_sendkey = ""
    _server_jiang_api_url = ""
    _enable_notify_types = []
    _notification_helper: NotificationHelper = None

    def init_plugin(self, config: dict = None):
        if hasattr(settings, 'VERSION_FLAG'):
            version = settings.VERSION_FLAG  # V2
        else:
            version = "v1"

        if version == "v2":
            self.setup_v2()
        else:
            self.setup_v1()

        if config:
            self._server_jiang_uid = config.get("server_jiang_uid", "")
            self._server_jiang_sendkey = config.get("server_jiang_sendkey", "")
            self._server_jiang_api_url = config.get("server_jiang_api_url", "")
            self._enable_notify_types = config.get("enable_notify_types", [])

            # 若 uid 未提供，尝试从 sendkey 中提取
            if not self._server_jiang_uid and self._server_jiang_sendkey:
                match = re.search(r'^sctp(\d+)t', self._server_jiang_sendkey)
                if match:
                    self._server_jiang_uid = match.group(1)

            # 若 API URL 未提供，使用 UID 和 SendKey 生成默认 URL
            if not self._server_jiang_api_url and self._server_jiang_uid and self._server_jiang_sendkey:
                self._server_jiang_api_url = f"https://{self._server_jiang_uid}.push.ft07.com/send/{self._server_jiang_sendkey}.send"
            # 若 UID 未提供，但有 API URL，尝试从 API URL 中提取 UID
            if not self._server_jiang_uid and self._server_jiang_api_url:
                match = re.search(r'https://(\d+).push.ft07.com', self._server_jiang_api_url)
                if match:
                    self._server_jiang_uid = match.group(1)

    def setup_v2(self):
        self._notification_helper = NotificationHelper()

    def setup_v1(self):
        pass

    def get_state(self) -> bool:
        """
        获取插件状态
        """
        return bool(self._server_jiang_api_url)

    def get_form(self) -> tuple[list[dict], dict[str, Any]]:
        """
        拼装插件配置页面
        """
        # 构造消息类型下拉选择元素
        select_items = [{
            "title": type.value,
            "value": type.name
        } for type in list(EventType) + list(ChainEventType) if type]

        elements = [
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
                                'component': 'VTextField',
                                'props': {
                                    'model': 'server_jiang_uid',
                                    'label': 'Server 酱 UID',
                                    'hint': '可从 SendKey 页面获取，或从 sendkey 中提取；与 API URL 二选一'
                                }
                            }
                        ]
                    },
                    {
                        'component': 'VCol',
                        'props': {
                            'cols': 12
                        },
                        'content': [
                            {
                                'component': 'VTextField',
                                'props': {
                                    'model': 'server_jiang_sendkey',
                                    'label': 'Server 酱 SendKey',
                                    'hint': '从 SendKey 页面获取'
                                }
                            }
                        ]
                    },
                    {
                        'component': 'VCol',
                        'props': {
                            'cols': 12
                        },
                        'content': [
                            {
                                'component': 'VTextField',
                                'props': {
                                    'model': 'server_jiang_api_url',
                                    'label': 'Server 酱 API URL',
                                    'hint': '可直接从 SendKey 页面复制；与 UID 二选一'
                                }
                            }
                        ]
                    },
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
                                    'items': select_items,
                                    'hint': '选择哪些类型的消息需要通过此渠道发送，缺省时不限制类型。'
                                }
                            }
                        ]
                    }
                ]
            }
        ]
        config_suggest = {
            "server_jiang_uid": "",
            "server_jiang_sendkey": "",
            "server_jiang_api_url": "",
            "enable_notify_types": []
        }
        return elements, config_suggest

    def send_server_jiang_notification(self, title: str, desp: str = "", tags: str = "", short: str = "", method='GET'):
        """
        发送 Server 酱通知
        """
        if not self._server_jiang_api_url:
            return False

        params = {
            "title": title,
            "desp": desp,
            "tags": tags,
            "short": short
        }
        # 过滤掉空参数
        params = {k: v for k, v in params.items() if v}

        if method == 'GET':
            # 对参数进行 URL 编码
            encoded_params = urlencode({k: quote(str(v)) if isinstance(v, str) else v for k, v in params.items()})
            url = f"{self._server_jiang_api_url}?{encoded_params}"
            try:
                response = requests.get(url)
                if response.status_code == 200:
                    result = response.json()
                    if result.get("errno") == 0:
                        return True
                    else:
                        print(f"Server 酱通知发送失败，错误信息: {result.get('errmsg')}")
                else:
                    print(f"Server 酱通知请求失败，状态码: {response.status_code}")
            except Exception as e:
                print(f"Server 酱通知发送出错: {e}")
        elif method == 'POST':
            try:
                response = requests.post(self._server_jiang_api_url, data=params)
                if response.status_code == 200:
                    result = response.json()
                    if result.get("errno") == 0:
                        return True
                    else:
                        print(f"Server 酱通知发送失败，错误信息: {result.get('errmsg')}")
                else:
                    print(f"Server 酱通知请求失败，状态码: {response.status_code}")
            except Exception as e:
                print(f"Server 酱通知发送出错: {e}")
        return False

    def handle_notification_event(self, event: Event):
        """
        处理通知事件
        """
        event_data = event.event_data
        event_type = event.event_type
        if self._enable_notify_types and event_type.name not in self._enable_notify_types:
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
