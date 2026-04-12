from typing import Any, List, Dict, Tuple, Optional
from urllib.parse import parse_qs

from app.core.event import eventmanager, Event
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import EventType, NotificationType
from app.utils.http import RequestUtils


class ServerChan(_PluginBase):
    # 插件名称
    plugin_name = "Server酱³通知"
    # 插件描述
    plugin_desc = "通过Server酱³发送消息通知，支持APP推送"
    # 插件图标
    plugin_icon = "icons/serverchan.png"
    # 插件版本
    plugin_version = "v1.6.0"
    # 插件作者
    plugin_author = "SilentReed"
    # 作者主页
    author_url = "https://github.com/SilentReed"
    # 插件配置项ID前缀
    plugin_config_prefix = "serverchan_"
    # 加载顺序
    plugin_order = 27
    # 可使用的用户级别
    auth_level = 1

    # 常量定义
    DEFAULT_PLUGIN_ORDER = 27
    DEFAULT_AUTH_LEVEL = 1
    REQUEST_TIMEOUT = 10  # 请求超时时间（秒）
    MAX_LOG_LENGTH = 200  # 日志最大长度

    # 私有属性
    _enabled = False
    _onlyonce = False
    _uid = None
    _sendkey = None
    _msgtypes = []

    def init_plugin(self, config: dict = None):
        if config:
            self._enabled = config.get("enabled")
            self._onlyonce = config.get("onlyonce")
            self._uid = config.get("uid")
            self._sendkey = config.get("sendkey")
            self._msgtypes = config.get("msgtypes") or []

        if self._onlyonce:
            self._onlyonce = False
            self._send_message("Server酱³通知测试", "插件已启用")

    def get_state(self) -> bool:
        if not self._enabled:
            return False
        if not self._uid or not self._sendkey:
            return False
        return True

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        pass

    def get_api(self) -> List[Dict[str, Any]]:
        pass

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        拼装插件配置页面，需要返回两块数据：1、页面配置；2、数据结构
        """
        # 遍历 NotificationType 枚举，生成消息类型选项
        MsgTypeOptions = self._build_message_type_options()
        
        return self._build_form_config(MsgTypeOptions), {
            "enabled": False,
            "onlyonce": False,
            "uid": "",
            "sendkey": "",
            "msgtypes": []
        }

    def _build_message_type_options(self) -> List[Dict[str, str]]:
        """构建消息类型选项"""
        options = []
        for item in NotificationType:
            options.append({
                "title": item.value,
                "value": item.name
            })
        return options

    def _build_form_config(self, msg_type_options: List[Dict[str, str]]) -> List[dict]:
        """构建表单配置"""
        return [
            {
                'component': 'VForm',
                'content': [
                    # 基本设置
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
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'enabled',
                                            'label': '启用插件',
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
                                            'model': 'onlyonce',
                                            'label': '测试插件（立即运行）',
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    # UID 和 SendKey
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'uid',
                                            'label': 'UID',
                                            'placeholder': '123456',
                                            'hint': 'Server酱³ 用户ID',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 8
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'sendkey',
                                            'label': 'SendKey',
                                            'placeholder': 'sctp123456txxxxxxxxxxxxx',
                                            'hint': '在 Server酱³ 官网获取',
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    # 消息类型选择
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
                                            'multiple': True,
                                            'chips': True,
                                            'model': 'msgtypes',
                                            'label': '消息类型（不选则接收所有）',
                                            'items': msg_type_options
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                ]
            }
        ]

    def get_page(self) -> List[dict]:
        pass

    def _send_message(self, title: str, text: str) -> Optional[Tuple[bool, str]]:
        """
        发送消息
        """
        try:
            if not self._validate_config():
                return False, "参数未配置"

            url = self._build_send_url()
            data = self._build_message_data(title, text)

            logger.info(f"Server酱³ 发送消息: {title}")
            res = RequestUtils(timeout=self.REQUEST_TIMEOUT).post_res(url, data=data)
            
            return self._handle_response(res, title)
            
        except ConnectionError as e:
            logger.error(f"Server酱³连接错误: {str(e)}")
            return False, f"连接错误: {str(e)}"
        except TimeoutError as e:
            logger.error(f"Server酱³请求超时: {str(e)}")
            return False, f"请求超时: {str(e)}"
        except ValueError as e:
            logger.error(f"Server酱³数据解析错误: {str(e)}")
            return False, f"数据解析错误: {str(e)}"
        except Exception as e:
            logger.error(f"Server酱³消息发送异常: {str(e)}")
            return False, f"发送异常: {str(e)}"

    def _validate_config(self) -> bool:
        """验证配置参数"""
        if not self._uid or not self._sendkey:
            logger.error("Server酱³ UID 或 SendKey 未配置")
            return False
        
        # 验证UID格式（应该是数字）
        if not str(self._uid).isdigit():
            logger.error("Server酱³ UID 格式错误，应为数字")
            return False
        
        # 验证SendKey格式
        if not self._sendkey.startswith('sctp'):
            logger.warning("Server酱³ SendKey 格式可能不正确")
        
        return True

    def _build_send_url(self) -> str:
        """构建发送URL"""
        return f"https://{self._uid}.push.ft07.com/send/{self._sendkey}.send"

    def _build_message_data(self, title: str, text: str) -> Dict[str, str]:
        """构建消息数据"""
        return {
            "title": title,
            "desp": f"{title}\n\n{text}",
        }

    def _handle_response(self, res, title: str) -> Tuple[bool, str]:
        """处理响应结果"""
        if not res:
            logger.warn("Server酱³请求失败，无响应")
            return False, "请求失败，无响应"
        
        if res.status_code != 200:
            logger.warn(f"Server酱³请求失败，状态码: {res.status_code}")
            if res.text:
                logger.warn(f"响应内容: {res.text[:self.MAX_LOG_LENGTH]}")
            return False, f"请求失败，状态码: {res.status_code}"
        
        try:
            result = res.json()
            if result.get("code") == 0:
                logger.info(f"Server酱³消息发送成功: {title}")
                return True, "发送成功"
            else:
                error_msg = result.get("message", "未知错误")
                logger.warn(f"Server酱³消息发送失败: {error_msg}")
                return False, error_msg
        except ValueError as e:
            logger.error(f"Server酱³响应解析失败: {str(e)}")
            return False, f"响应解析失败: {str(e)}"

    @eventmanager.register(EventType.NoticeMessage)
    def send(self, event: Event):
        """
        消息发送事件
        """
        if not self.get_state():
            logger.debug("Server酱³ 插件未启用或参数未配置")
            return

        if not event.event_data:
            logger.debug("Server酱³ 事件数据为空")
            return

        msg_body = event.event_data
        
        # 标题
        title = msg_body.get("title")
        # 文本
        text = msg_body.get("text")

        if not title and not text:
            logger.warn("Server酱³ 标题和内容不能同时为空")
            return

        # 消息类型过滤
        if not self._should_send_message(msg_body):
            return

        logger.info(f"Server酱³ 收到消息: {title}")
        return self._send_message(title, text)

    def _should_send_message(self, msg_body: Dict) -> bool:
        """判断是否应该发送消息"""
        msg_type = msg_body.get("type")
        if not msg_type or not self._msgtypes:
            return True
        
        # 如果配置了消息类型，则只发送选中的类型
        if isinstance(msg_type, NotificationType):
            if msg_type.name not in self._msgtypes:
                logger.debug(f"Server酱³ 消息类型 {msg_type.value} 未开启，跳过")
                return False
        elif isinstance(msg_type, str):
            if msg_type not in self._msgtypes:
                logger.debug(f"Server酱³ 消息类型 {msg_type} 未开启，跳过")
                return False
        
        return True

    def stop_service(self):
        """
        退出插件
        """
        pass