from typing import Any, Optional
import asyncio
import json
import re
from datetime import datetime

import aiohttp
from app.core.event import eventmanager, Event, EventType
from app.plugins import _PluginBase
from app.schemas import NotificationType


class ServerChan(_PluginBase):
    # 插件信息
    plugin_type = "notify"
    plugin_name = "Server酱³通知"
    plugin_desc = "通过Server酱³发送消息通知，支持APP推送"
    plugin_version = "1.0.2"

    # 插件配置项
    sendkey: str = ""
    enabled: bool = False
    
    # 事件开关配置
    notify_download_added: bool = True      # 下载任务添加
    notify_download_deleted: bool = True   # 下载任务删除
    notify_transfer_complete: bool = True   # 媒体整理完成
    notify_subscribe_complete: bool = True  # 订阅完成
    notify_site_refreshed: bool = False    # 站点刷新
    notify_system_error: bool = True       # 系统错误
    notify_user_message: bool = True        # 用户消息
    notify_notice_message: bool = True      # 通知消息（综合）

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._aio_session: Optional[aiohttp.ClientSession] = None
        self._uid: Optional[str] = None

    @property
    def aio_session(self) -> aiohttp.ClientSession:
        if self._aio_session is None or self._aio_session.closed:
            self._aio_session = aiohttp.ClientSession()
        return self._aio_session
    
    def _parse_uid(self) -> Optional[str]:
        """从 sendkey 中提取 uid"""
        if not self.sendkey:
            return None
        # sendkey 格式: sctp{uid}t...
        match = re.match(r'^sctp(\d+)t', self.sendkey)
        if match:
            return match.group(1)
        return None

    def get_plugin_desc(self) -> dict:
        return {
            "type": self.plugin_type,
            "name": self.plugin_name,
            "desc": self.plugin_desc,
            "version": self.plugin_version,
        }

    def get_config_form(self) -> Optional[list]:
        """
        V2版本配置表单
        """
        return [
            {
                "component": "v-switch",
                "props": {
                    "label": "启用插件",
                    "model": self.enabled,
                    "key": "enabled",
                }
            },
            {
                "component": "v-text-field",
                "props": {
                    "label": "Server酱³ SendKey",
                    "model": self.sendkey,
                    "key": "sendkey",
                    "placeholder": "sctp123456txxxxxxxxxxxxx",
                    "hint": "在 Server酱³ 官网获取的 SendKey",
                    "persistent-hint": True,
                }
            },
            {
                "component": "v-divider",
                "props": {
                    "class": "my-2"
                }
            },
            {
                "component": "v-subheader",
                "props": {
                    "class": "py-0"
                },
                "text": "通知事件配置"
            },
            {
                "component": "v-switch",
                "props": {
                    "label": "下载任务添加通知",
                    "model": self.notify_download_added,
                    "key": "notify_download_added",
                }
            },
            {
                "component": "v-switch",
                "props": {
                    "label": "下载任务删除通知",
                    "model": self.notify_download_deleted,
                    "key": "notify_download_deleted",
                }
            },
            {
                "component": "v-switch",
                "props": {
                    "label": "媒体整理完成通知",
                    "model": self.notify_transfer_complete,
                    "key": "notify_transfer_complete",
                }
            },
            {
                "component": "v-switch",
                "props": {
                    "label": "订阅完成通知",
                    "model": self.notify_subscribe_complete,
                    "key": "notify_subscribe_complete",
                }
            },
            {
                "component": "v-switch",
                "props": {
                    "label": "站点刷新通知",
                    "model": self.notify_site_refreshed,
                    "key": "notify_site_refreshed",
                }
            },
            {
                "component": "v-switch",
                "props": {
                    "label": "系统错误通知",
                    "model": self.notify_system_error,
                    "key": "notify_system_error",
                }
            },
            {
                "component": "v-switch",
                "props": {
                    "label": "用户消息通知",
                    "model": self.notify_user_message,
                    "key": "notify_user_message",
                }
            },
            {
                "component": "v-switch",
                "props": {
                    "label": "综合通知消息",
                    "model": self.notify_notice_message,
                    "key": "notify_notice_message",
                }
            },
        ]

    async def send_message(self, title: str, content: str, 
                          notification_type: NotificationType = NotificationType.Info,
                          tags: str = "") -> bool:
        """
        发送消息到 Server酱³
        API: https://<uid>.push.ft07.com/send/<sendkey>.send
        """
        if not self.sendkey:
            self.systemmessage("Server酱³ SendKey 未配置")
            return False

        # 提取 uid
        uid = self._parse_uid()
        if not uid:
            self.systemmessage("SendKey 格式错误，应为 sctp{uid}t 格式")
            return False

        try:
            url = f"https://{uid}.push.ft07.com/send/{self.sendkey}.send"
            
            # 根据通知类型添加不同的前缀
            type_emoji = {
                NotificationType.Info: "ℹ️",
                NotificationType.Warning: "⚠️",
                NotificationType.Error: "❌",
                NotificationType.Success: "✅",
            }
            prefix = type_emoji.get(notification_type, "")
            
            # 格式化内容
            desp = f"{title}\n\n{content}"
            
            data = {
                "title": f"{prefix} {title}",
                "desp": desp,
            }
            
            # 添加标签
            if tags:
                data["tags"] = tags

            async with self.aio_session.post(url, data=data, timeout=10) as response:
                result = await response.json()
                
                # Server酱³ 返回 code: 0 表示成功
                if result.get("code") == 0:
                    self.systemmessage(f"Server酱³消息发送成功: {title}")
                    return True
                else:
                    error_msg = result.get("message", "未知错误")
                    self.systemmessage(f"Server酱³消息发送失败: {error_msg}")
                    return False
                    
        except asyncio.TimeoutError:
            self.systemmessage("Server酱³消息发送超时")
            return False
        except Exception as e:
            self.systemmessage(f"Server酱³消息发送异常: {str(e)}")
            return False

    def build_message(self, event_data: dict, event_type: str) -> tuple[str, str, NotificationType, str]:
        """
        构建消息内容
        返回: (title, content, notification_type, tags)
        """
        title = "MoviePilot 通知"
        content = ""
        notify_type = NotificationType.Info
        tags = "MoviePilot"
        
        if event_type == "download.added":
            title = "📥 下载任务已添加"
            content = f"名称: {event_data.get('name', '未知')}\n"
            content += f"类型: {event_data.get('type', '未知')}\n"
            if event_data.get('size'):
                content += f"大小: {event_data.get('size')}\n"
            tags = "下载|MoviePilot"
                
        elif event_type == "download.deleted":
            title = "🗑️ 下载任务已删除"
            content = f"名称: {event_data.get('name', '未知')}\n"
            content += f"类型: {event_data.get('type', '未知')}\n"
            notify_type = NotificationType.Warning
            tags = "下载|MoviePilot"
            
        elif event_type == "transfer.complete":
            title = "✅ 媒体整理完成"
            content = f"名称: {event_data.get('name', '未知')}\n"
            content += f"类型: {event_data.get('type', '未知')}\n"
            content += f"路径: {event_data.get('path', '未知')}\n"
            notify_type = NotificationType.Success
            tags = "整理|MoviePilot"
            
        elif event_type == "subscribe.complete":
            title = "📺 订阅已完成"
            content = f"名称: {event_data.get('name', '未知')}\n"
            content += f"类型: {event_data.get('type', '未知')}\n"
            if event_data.get('count'):
                content += f"数量: {event_data.get('count')}\n"
            notify_type = NotificationType.Success
            tags = "订阅|MoviePilot"
            
        elif event_type == "site.refreshed":
            title = "🔄 站点已刷新"
            content = f"站点: {event_data.get('name', '未知')}\n"
            content += f"状态: {event_data.get('status', '完成')}\n"
            tags = "站点|MoviePilot"
            
        elif event_type == "system.error":
            title = "❌ 系统错误"
            content = f"错误: {event_data.get('error', '未知错误')}\n"
            if event_data.get('module'):
                content += f"模块: {event_data.get('module')}\n"
            notify_type = NotificationType.Error
            tags = "错误|MoviePilot"
            
        elif event_type == "user.message":
            title = "💬 用户消息"
            content = f"用户: {event_data.get('userid', '未知')}\n"
            content += f"消息: {event_data.get('text', '未知')}\n"
            tags = "消息|MoviePilot"
            
        elif event_type == "notice.message":
            title = event_data.get('title', 'MoviePilot 通知')
            content = event_data.get('text', '')
            notify_type = event_data.get('type', NotificationType.Info)
            tags = "通知|MoviePilot"
            
        else:
            # 通用处理
            title = f"MoviePilot: {event_type}"
            content = json.dumps(event_data, ensure_ascii=False, indent=2)
        
        return title, content, notify_type, tags

    # ==================== V2 事件监听器 ====================

    @eventmanager.register(EventType.DownloadAdded)
    async def handle_download_added(self, event: Event) -> None:
        """下载任务添加事件"""
        if not self.enabled or not self.notify_download_added:
            return
        event_data = event.event_data or {}
        title, content, notify_type, tags = self.build_message(event_data, "download.added")
        await self.send_message(title, content, notify_type, tags)

    @eventmanager.register(EventType.DownloadDeleted)
    async def handle_download_deleted(self, event: Event) -> None:
        """下载任务删除事件"""
        if not self.enabled or not self.notify_download_deleted:
            return
        event_data = event.event_data or {}
        title, content, notify_type, tags = self.build_message(event_data, "download.deleted")
        await self.send_message(title, content, notify_type, tags)

    @eventmanager.register(EventType.TransferComplete)
    async def handle_transfer_complete(self, event: Event) -> None:
        """媒体整理完成事件"""
        if not self.enabled or not self.notify_transfer_complete:
            return
        event_data = event.event_data or {}
        title, content, notify_type, tags = self.build_message(event_data, "transfer.complete")
        await self.send_message(title, content, notify_type, tags)

    @eventmanager.register(EventType.SubscribeComplete)
    async def handle_subscribe_complete(self, event: Event) -> None:
        """订阅完成事件"""
        if not self.enabled or not self.notify_subscribe_complete:
            return
        event_data = event.event_data or {}
        title, content, notify_type, tags = self.build_message(event_data, "subscribe.complete")
        await self.send_message(title, content, notify_type, tags)

    @eventmanager.register(EventType.SiteRefreshed)
    async def handle_site_refreshed(self, event: Event) -> None:
        """站点刷新事件"""
        if not self.enabled or not self.notify_site_refreshed:
            return
        event_data = event.event_data or {}
        title, content, notify_type, tags = self.build_message(event_data, "site.refreshed")
        await self.send_message(title, content, notify_type, tags)

    @eventmanager.register(EventType.SystemError)
    async def handle_system_error(self, event: Event) -> None:
        """系统错误事件"""
        if not self.enabled or not self.notify_system_error:
            return
        event_data = event.event_data or {}
        title, content, notify_type, tags = self.build_message(event_data, "system.error")
        await self.send_message(title, content, notify_type, tags)

    @eventmanager.register(EventType.UserMessage)
    async def handle_user_message(self, event: Event) -> None:
        """用户消息事件"""
        if not self.enabled or not self.notify_user_message:
            return
        event_data = event.event_data or {}
        title, content, notify_type, tags = self.build_message(event_data, "user.message")
        await self.send_message(title, content, notify_type, tags)

    @eventmanager.register(EventType.NoticeMessage)
    async def handle_notice_message(self, event: Event) -> None:
        """综合通知消息事件"""
        if not self.enabled or not self.notify_notice_message:
            return
        event_data = event.event_data or {}
        title, content, notify_type, tags = self.build_message(event_data, "notice.message")
        await self.send_message(title, content, notify_type, tags)

    def stop(self):
        """停止插件"""
        if self._aio_session and not self._aio_session.closed:
            try:
                asyncio.create_task(self._aio_session.close())
            except RuntimeError:
                # 如果在事件循环外
                pass
        super().stop()
