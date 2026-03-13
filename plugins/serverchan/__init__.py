from typing import Any, Optional
import asyncio
import json
from datetime import datetime

import aiohttp
from app import schemas
from app.core.config import settings
from app.core.event import eventmanager, Event, EventType
from app.plugins import _PluginBase
from app.schemas import NotificationType


class ServerChan(_PluginBase):
    # 插件信息
    plugin_type = "notify"
    plugin_name = "Server酱通知"
    plugin_desc = "通过Server酱发送消息通知，支持多种事件触发"
    plugin_version = "1.0.0"

    # 插件配置项
    sckey: str = ""
    enabled: bool = False
    
    # 事件开关配置
    notify_download_added: bool = True      # 下载任务添加
    notify_download_deleted: bool = True   # 下载任务删除
    notify_transfer_complete: bool = True # 媒体整理完成
    notify_subscribe_complete: bool = True # 订阅完成
    notify_site_refreshed: bool = False   # 站点刷新
    notify_system_error: bool = True       # 系统错误
    notify_user_message: bool = True       # 用户消息
    notify_notice_message: bool = True     # 通知消息（综合）

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._aio_session: Optional[aiohttp.ClientSession] = None

    @property
    def aio_session(self) -> aiohttp.ClientSession:
        if self._aio_session is None or self._aio_session.closed:
            self._aio_session = aiohttp.ClientSession()
        return self._aio_session

    def get_plugin_desc(self) -> dict:
        return {
            "type": self.plugin_type,
            "name": self.plugin_name,
            "desc": self.plugin_desc,
            "version": self.plugin_version,
        }

    def get_schema(self) -> list[schemas.PluginConfigItem]:
        return [
            {
                "key": "sckey",
                "name": "Server酱 SCKEY",
                "desc": "在 Server酱 官网获取的 SCKEY",
                "type": "string",
                "required": True,
            },
            {
                "key": "enabled",
                "name": "启用插件",
                "desc": "是否启用 Server酱 通知",
                "type": "switch",
                "required": False,
            },
            {
                "key": "notify_download_added",
                "name": "下载任务添加通知",
                "desc": "当下载任务添加时发送通知",
                "type": "switch",
                "required": False,
            },
            {
                "key": "notify_download_deleted",
                "name": "下载任务删除通知",
                "desc": "当下载任务删除时发送通知",
                "type": "switch",
                "required": False,
            },
            {
                "key": "notify_transfer_complete",
                "name": "媒体整理完成通知",
                "desc": "当媒体文件整理完成时发送通知",
                "type": "switch",
                "required": False,
            },
            {
                "key": "notify_subscribe_complete",
                "name": "订阅完成通知",
                "desc": "当订阅完成时发送通知",
                "type": "switch",
                "required": False,
            },
            {
                "key": "notify_site_refreshed",
                "name": "站点刷新通知",
                "desc": "当站点刷新时发送通知",
                "type": "switch",
                "required": False,
            },
            {
                "key": "notify_system_error",
                "name": "系统错误通知",
                "desc": "当发生系统错误时发送通知",
                "type": "switch",
                "required": False,
            },
            {
                "key": "notify_user_message",
                "name": "用户消息通知",
                "desc": "当收到用户消息时发送通知",
                "type": "switch",
                "required": False,
            },
            {
                "key": "notify_notice_message",
                "name": "综合通知消息",
                "desc": "接收所有通知消息（总开关）",
                "type": "switch",
                "required": False,
            },
        ]

    async def send_message(self, title: str, content: str, 
                          notification_type: NotificationType = NotificationType.Info) -> bool:
        """
        发送消息到 Server酱
        """
        if not self.sckey:
            self.systemmessage("Server酱 SCKEY 未配置")
            return False

        try:
            url = f"https://sct.ftqq.com/{self.sckey}.send"
            
            # 构建消息内容
            text = f"{title}\n\n{content}"
            
            # 根据通知类型添加不同的前缀
            type_emoji = {
                NotificationType.Info: "ℹ️",
                NotificationType.Warning: "⚠️",
                NotificationType.Error: "❌",
                NotificationType.Success: "✅",
            }
            prefix = type_emoji.get(notification_type, "")
            
            data = {
                "title": f"{prefix} {title}",
                "content": text,
            }

            async with self.aio_session.post(url, data=data, timeout=10) as response:
                result = await response.json()
                
                if result.get("code") == 0:
                    self.systemmessage(f"Server酱消息发送成功: {title}")
                    return True
                else:
                    error_msg = result.get("message", "未知错误")
                    self.systemmessage(f"Server酱消息发送失败: {error_msg}")
                    return False
                    
        except asyncio.TimeoutError:
            self.systemmessage("Server酱消息发送超时")
            return False
        except Exception as e:
            self.systemmessage(f"Server酱消息发送异常: {str(e)}")
            return False

    def build_message(self, event_data: dict, event_type: str) -> tuple[str, str, NotificationType]:
        """
        构建消息内容
        返回: (title, content, notification_type)
        """
        title = "MoviePilot 通知"
        content = ""
        notify_type = NotificationType.Info
        
        if event_type == "download.added":
            title = "📥 下载任务已添加"
            content = f"名称: {event_data.get('name', '未知')}\n"
            content += f"类型: {event_data.get('type', '未知')}\n"
            if event_data.get('size'):
                content += f"大小: {event_data.get('size')}\n"
                
        elif event_type == "download.deleted":
            title = "🗑️ 下载任务已删除"
            content = f"名称: {event_data.get('name', '未知')}\n"
            content += f"类型: {event_data.get('type', '未知')}\n"
            notify_type = NotificationType.Warning
            
        elif event_type == "transfer.complete":
            title = "✅ 媒体整理完成"
            content = f"名称: {event_data.get('name', '未知')}\n"
            content += f"类型: {event_data.get('type', '未知')}\n"
            content += f"路径: {event_data.get('path', '未知')}\n"
            notify_type = NotificationType.Success
            
        elif event_type == "subscribe.complete":
            title = "📺 订阅已完成"
            content = f"名称: {event_data.get('name', '未知')}\n"
            content += f"类型: {event_data.get('type', '未知')}\n"
            if event_data.get('count'):
                content += f"数量: {event_data.get('count')}\n"
            notify_type = NotificationType.Success
            
        elif event_type == "site.refreshed":
            title = "🔄 站点已刷新"
            content = f"站点: {event_data.get('name', '未知')}\n"
            content += f"状态: {event_data.get('status', '完成')}\n"
            
        elif event_type == "system.error":
            title = "❌ 系统错误"
            content = f"错误: {event_data.get('error', '未知错误')}\n"
            if event_data.get('module'):
                content += f"模块: {event_data.get('module')}\n"
            notify_type = NotificationType.Error
            
        elif event_type == "user.message":
            title = "💬 用户消息"
            content = f"用户: {event_data.get('userid', '未知')}\n"
            content += f"消息: {event_data.get('text', '未知')}\n"
            
        elif event_type == "notice.message":
            title = event_data.get('title', 'MoviePilot 通知')
            content = event_data.get('text', '')
            notify_type = event_data.get('type', NotificationType.Info)
            
        else:
            # 通用处理
            title = f"MoviePilot: {event_type}"
            content = json.dumps(event_data, ensure_ascii=False, indent=2)
        
        return title, content, notify_type

    # ==================== 事件监听器 ====================

    @eventmanager.register(EventType.DownloadAdded)
    async def handle_download_added(self, event: Event) -> None:
        """下载任务添加事件"""
        if not self.enabled or not self.notify_download_added:
            return
        event_data = event.event_data or {}
        title, content, notify_type = self.build_message(event_data, "download.added")
        await self.send_message(title, content, notify_type)

    @eventmanager.register(EventType.DownloadDeleted)
    async def handle_download_deleted(self, event: Event) -> None:
        """下载任务删除事件"""
        if not self.enabled or not self.notify_download_deleted:
            return
        event_data = event.event_data or {}
        title, content, notify_type = self.build_message(event_data, "download.deleted")
        await self.send_message(title, content, notify_type)

    @eventmanager.register(EventType.TransferComplete)
    async def handle_transfer_complete(self, event: Event) -> None:
        """媒体整理完成事件"""
        if not self.enabled or not self.notify_transfer_complete:
            return
        event_data = event.event_data or {}
        title, content, notify_type = self.build_message(event_data, "transfer.complete")
        await self.send_message(title, content, notify_type)

    @eventmanager.register(EventType.SubscribeComplete)
    async def handle_subscribe_complete(self, event: Event) -> None:
        """订阅完成事件"""
        if not self.enabled or not self.notify_subscribe_complete:
            return
        event_data = event.event_data or {}
        title, content, notify_type = self.build_message(event_data, "subscribe.complete")
        await self.send_message(title, content, notify_type)

    @eventmanager.register(EventType.SiteRefreshed)
    async def handle_site_refreshed(self, event: Event) -> None:
        """站点刷新事件"""
        if not self.enabled or not self.notify_site_refreshed:
            return
        event_data = event.event_data or {}
        title, content, notify_type = self.build_message(event_data, "site.refreshed")
        await self.send_message(title, content, notify_type)

    @eventmanager.register(EventType.SystemError)
    async def handle_system_error(self, event: Event) -> None:
        """系统错误事件"""
        if not self.enabled or not self.notify_system_error:
            return
        event_data = event.event_data or {}
        title, content, notify_type = self.build_message(event_data, "system.error")
        await self.send_message(title, content, notify_type)

    @eventmanager.register(EventType.UserMessage)
    async def handle_user_message(self, event: Event) -> None:
        """用户消息事件"""
        if not self.enabled or not self.notify_user_message:
            return
        event_data = event.event_data or {}
        title, content, notify_type = self.build_message(event_data, "user.message")
        await self.send_message(title, content, notify_type)

    @eventmanager.register(EventType.NoticeMessage)
    async def handle_notice_message(self, event: Event) -> None:
        """综合通知消息事件"""
        if not self.enabled or not self.notify_notice_message:
            return
        event_data = event.event_data or {}
        title, content, notify_type = self.build_message(event_data, "notice.message")
        await self.send_message(title, content, notify_type)

    def stop(self):
        """停止插件"""
        if self._aio_session and not self._aio_session.closed:
            try:
                asyncio.create_task(self._aio_session.close())
            except RuntimeError:
                # 如果在事件循环外
                pass
        super().stop()
