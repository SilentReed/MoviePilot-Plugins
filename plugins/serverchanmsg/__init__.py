from app.core.event import eventmanager, Event
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import EventType, NotificationType
from serverchan_sdk import sc_send
import threading

lock = threading.Lock()


class ServerChanMsg(_PluginBase):
    # 插件名称
    plugin_name = "Server酱消息通知"
    # 插件描述
    plugin_desc = "支持使用Server酱发送消息通知。"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/SilentReed/MoviePilot-Plugins/main/icons/serverchan.png"
    # 插件版本
    plugin_version = "1.2"
    # 插件作者
    plugin_author = "SilentReed"
    # 作者主页
    author_url = "https://github.com/SilentReed"
    # 插件配置项ID前缀
    plugin_config_prefix = "serverchanmsg_"
    # 加载顺序
    plugin_order = 31
    # 可使用的用户级别
    auth_level = 1

    # 私有属性
    _enabled = False
    _onlyonce = False
    _send_image_enabled = False

    _serverchan_key = None
    _msgtypes = []

    _scheduler = None
    _event = threading.Event()

    def init_plugin(self, config: dict = None):
        if config:
            self._enabled = config.get("enabled")
            self._onlyonce = config.get("onlyonce")
            self._send_image_enabled = config.get("send_image_enabled")

            self._serverchan_key = config.get("serverchan_key")
            self._msgtypes = config.get("msgtypes") or []

        if self._onlyonce:
            flag = self.send_msg(title="Server酱消息通知测试",
                                 text="Server酱消息通知测试成功！",
                                 image="https://the7.ft07.com/sct/images/logo.png")
            if flag:
                self.systemmessage.put("Server酱消息通知测试成功！")
            self._onlyonce = False

        self.__update_config()

    def __update_config(self):
        """
        更新配置
        :return:
        """
        config = {
            "enabled": self._enabled,
            "onlyonce": self._onlyonce,
            "send_image_enabled": self._send_image_enabled,
            "serverchan_key": self._serverchan_key,
            "msgtypes": self._msgtypes,
        }
        self.update_config(config)

    def get_state(self) -> bool:
        return self._enabled and (True if self._serverchan_key else False)

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
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4,
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'enabled',
                                            'label': '启用插件',
                                            'hint': '开启后插件将处于激活状态',
                                            'persistent-hint': True,
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4,
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'onlyonce',
                                            'label': '立刻发送测试',
                                            'hint': '一次性任务，运行后自动关闭',
                                            'persistent-hint': True,
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4,
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'send_image_enabled',
                                            'label': '发送图片',
                                            'hint': '可选；关闭时，不发送图片',
                                            'persistent-hint': True,
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
                                        'component': 'VAlert',
                                        'props': {
                                            'type': 'info',
                                            'variant': 'tonal',
                                            'style': 'white-space: pre-line;',
                                            'text': '图片消息发送的内容为图片的URL地址，如果图片URL在接收端存在污染或者屏蔽，会导致图片无法显示的问题。'
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
                                    'cols': 12,
                                    'md': 12
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'serverchan_key',
                                            'label': 'ServerChan 密钥',
                                            'placeholder': 'token: xxxxxxxxxxxxxx',
                                            'hint': '必填；ServerChan的SendKey密钥或AppKey',
                                            'persistent-hint': True,
                                            'clearable': True,
                                        }
                                    }
                                ]
                            },
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
                                            'multiple': True,
                                            'chips': True,
                                            'model': 'msgtypes',
                                            'label': '消息类型',
                                            'items': MsgTypeOptions,
                                            'clearable': True,
                                            'hint': '自定义需要接受并发送的消息类型',
                                            'persistent-hint': True,
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
            "send_image_enabled": False,
            "serverchan_key": "",
            'msgtypes': [],
        }

    def get_page(self) -> List[dict]:
        pass

    @eventmanager.register(EventType.NoticeMessage)
    def send(self, event: Event):
        """
        消息发送事件
        """
        if not self.get_state():
            return

        if not event.event_data:
            return

        msg_body = event.event_data
        # 渠道
        channel = msg_body.get("channel")
        if channel:
            return
        # 类型
        msg_type: NotificationType = msg_body.get("type")
        # 标题
        title = msg_body.get("title")
        # 文本
        text = msg_body.get("text")
        # 图片
        image = msg_body.get("image")

        if not title and not text:
            logger.warn("标题和内容不能同时为空")
            return

        if (msg_type and self._msgtypes
                and msg_type.name not in self._msgtypes):
            logger.info(f"消息类型 {msg_type.value} 未开启消息发送")
            return

        self.send_msg(title=title, text=text, image=image)

    def send_msg(self, title, text, image=None):
        """
        发送消息
        """
        with lock:
            try:
                if not self._serverchan_key:
                    raise Exception("未添加ServerChan密钥")

                if self._send_image_enabled and image:
                    content = text + '\n ![image](' + image + ')'
                else:
                    content = text

                options = {}
                response = sc_send(self._serverchan_key, title, content, options)

                if response and response.get('code') == 0:
                    logger.info("ServerChan消息发送成功")
                    return True
                else:
                    error_msg = response.get('message') if response else "未获取到返回信息"
                    raise Exception(f"ServerChan消息发送失败：{error_msg}")
            except Exception as msg_e:
                logger.error(f"ServerChan消息发送失败 - {str(msg_e)}")
                return False

    def stop_service(self):
        """
        退出插件
        """
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._event.set()
                    self._scheduler.shutdown(wait=False)
                    self._event.clear()
                self._scheduler = None
        except Exception as e:
            logger.error(str(e))