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
    plugin_version = "1.1.0"
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
        MsgTypeOptions = []
        for item in NotificationType:
            MsgTypeOptions.append({
                "title": item.value,
                "value": item.name
            })
        
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
                                            'items': MsgTypeOptions
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                ]
            }
        ], {
            "enabled": False,
            "onlyonce": False,
            "uid": "",
            "sendkey": "",
            "msgtypes": []
        }

    def get_page(self) -> List[dict]:
        pass

    def _send_message(self, title: str, text: str) -> Optional[Tuple[bool, str]]:
        """
        发送消息
        """
        try:
            if not self._uid or not self._sendkey:
                logger.error("Server酱³ UID 或 SendKey 未配置")
                return False, "参数未配置"

            url = f"https://{self._uid}.push.ft07.com/send/{self._sendkey}.send"
            
            data = {
                "title": title,
                "desp": f"{title}\n\n{text}",
            }

            logger.info(f"Server酱³ 发送消息: {title}")
            res = RequestUtils().post_res(url, data=data)
            if res and res.status_code == 200:
                result = res.json()
                if result.get("code") == 0:
                    logger.info(f"Server酱³消息发送成功: {title}")
                    return True, "发送成功"
                else:
                    error_msg = result.get("message", "未知错误")
                    logger.warn(f"Server酱³消息发送失败: {error_msg}")
                    return False, error_msg
            else:
                status = res.status_code if res else "None"
                logger.warn(f"Server酱³消息发送失败，状态码: {status}")
                if res is not None:
                    logger.warn(f"响应内容: {res.text[:200]}")
                return False, f"请求失败，状态码: {status}"
                
        except Exception as e:
            logger.error(f"Server酱³消息发送异常: {str(e)}")
            return False, str(e)

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
        msg_type = msg_body.get("type")
        if msg_type and self._msgtypes:
            # 如果配置了消息类型，则只发送选中的类型
            if isinstance(msg_type, NotificationType):
                if msg_type.name not in self._msgtypes:
                    logger.debug(f"Server酱³ 消息类型 {msg_type.value} 未开启，跳过")
                    return
            elif isinstance(msg_type, str):
                if msg_type not in self._msgtypes:
                    logger.debug(f"Server酱³ 消息类型 {msg_type} 未开启，跳过")
                    return

        logger.info(f"Server酱³ 收到消息: {title}")
        return self._send_message(title, text)

    def stop_service(self):
        """
        退出插件
        """
        pass
