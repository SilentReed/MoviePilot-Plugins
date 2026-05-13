"""
MoviePilot V2 Plugin - 绿联论坛积分查询 (增强版)
每日定时查询绿联论坛 (club.ugnas.com) 积分变化并推送通知

增强功能：
- OAuth API 自动登录（无需手动抓Cookie）
- Playwright 浏览器兜底登录
- 用户资料展示（头像、用户组等）
- Cookie 自动刷新
- 异步HTTP请求
- 自动重试机制
- 积分趋势分析
- 增强的界面展示
"""

import re
import time
import json
import asyncio
import uuid
import base64
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import aiohttp
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.log import logger
from app.plugins import _PluginBase


class UgnasCredits(_PluginBase):
    """绿联论坛积分查询插件（增强版）"""

    plugin_name: str = "绿联论坛积分助手"
    plugin_desc: str = "每日定时查询绿联论坛积分变化并推送通知，支持自动登录"
    plugin_icon: str = "https://raw.githubusercontent.com/SilentReed/MoviePilot-Plugins-UgnasCredits/main/plugins.v2/ugnascredits/icons/ugnascredits.svg"
    plugin_version: str = "2.0.1"
    plugin_author: str = "SilentReed"
    author_url: str = "https://github.com/SilentReed"
    plugin_config_prefix: str = "ugnascredits_"
    plugin_order: int = 50
    auth_level: int = 1

    BASE_URL: str = "https://club.ugnas.com"
    API_BASE: str = "https://api-zh.ugnas.com"
    REQUEST_TIMEOUT: int = 15
    MAX_LOG_LENGTH: int = 200

    def init_plugin(self, config: Optional[Dict[str, Any]] = None) -> None:
        """插件初始化"""
        # 初始化默认值（必须在 stop_service 之前）
        self._enabled = False
        self._onlyonce = False
        self._cron = "0 8 * * *"
        self._cookie = ""
        self._username = ""
        self._password = ""
        self._uid = ""
        self._notify = True
        self._retry_times = 3
        self._retry_delay = 2
        self._timeout = 30
        self._history_days = 30
        self._scheduler: Optional[BackgroundScheduler] = None

        self.stop_service()

        self._data_file: Path = Path(settings.ROOT_PATH) / "plugins" / "data" / "ugnascredits" / "credits.json"
        self._last_run_time: str = ""
        self._last_run_status: bool = False
        self._last_run_message: str = "" 

        if config:
            self._enabled = config.get("enabled", False)
            self._onlyonce = config.get("onlyonce", False)
            self._cron = config.get("cron", "0 8 * * *")
            self._cookie = (config.get("cookie") or "").strip()
            self._username = (config.get("username") or "").strip()
            self._password = (config.get("password") or "").strip()
            self._uid = (config.get("uid") or "").strip()
            self._notify = config.get("notify", True)
            self._retry_times = config.get("retry_times", 3)
            self._retry_delay = config.get("retry_delay", 2)
            self._timeout = config.get("timeout", 30)
            try:
                self._history_days = int(config.get("history_days", 30))
            except Exception:
                self._history_days = 30

        if self._onlyonce:
            self._onlyonce = False
            self._save_config()
            self._scheduler = BackgroundScheduler(timezone=settings.TZ)
            self._scheduler.add_job(
                func=self._run_task,
                trigger='date',
                run_date=datetime.now() + timedelta(seconds=3),
                name="绿联论坛积分查询"
            )
            if self._scheduler.get_jobs():
                self._scheduler.start()

        if self._enabled and self._cron:
            if not self._scheduler:
                self._scheduler = BackgroundScheduler(timezone=settings.TZ)
            try:
                trigger = CronTrigger.from_crontab(self._cron, timezone=settings.TZ)
            except Exception:
                trigger = CronTrigger(hour=8, minute=0, timezone=settings.TZ)
            self._scheduler.add_job(
                self._run_task,
                trigger=trigger,
                name="绿联论坛积分查询"
            )
            self._scheduler.start()
            logger.info(f"定时服务已启动: {self._cron}")

    def _save_config(self) -> None:
        """保存插件配置"""
        self.update_config({
            "enabled": self._enabled,
            "onlyonce": self._onlyonce,
            "cron": self._cron,
            "cookie": self._cookie,
            "username": self._username,
            "password": self._password,
            "uid": self._uid,
            "notify": self._notify,
            "retry_times": self._retry_times,
            "retry_delay": self._retry_delay,
            "timeout": self._timeout,
            "history_days": self._history_days,
        })

    def _run_task(self) -> None:
        """执行积分查询任务"""
        try:
            asyncio.create_task(self._do_task_async())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(self._do_task_async())
            loop.close()

    async def _do_task_async(self) -> Tuple[bool, str]:
        """执行积分查询任务"""
        logger.info("开始执行绿联论坛积分查询...")
        self._last_run_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        today = datetime.now().strftime("%Y-%m-%d")

        try:
            # 尝试自动登录刷新Cookie
            if not self._cookie or '6LQh_2132_auth=' not in self._cookie:
                logger.info("Cookie无效或为空，尝试自动登录...")
                if self._username and self._password:
                    login_ok = await self._auto_login()
                    if login_ok:
                        logger.info("自动登录成功")
                    else:
                        logger.warning("自动登录失败")

            # 获取用户资料和积分
            info = await self._fetch_user_profile()
            if not info:
                msg = "❌ 获取用户资料失败，请检查Cookie或账号密码"
                self._last_run_status = False
                self._last_run_message = msg
                if self._notify:
                    self.post_message(mtype="插件", title="绿联论坛积分查询", text=msg)
                return False, msg

            credits_now = info.get('points', 0)
            logger.info(f"获取积分成功: {credits_now}")

            # 加载历史数据
            data = self._load_data()
            records = data.get("records", [])

            # 计算积分变化
            last_record = records[-1] if records else None
            change_from_last = 0
            if last_record:
                change_from_last = credits_now - last_record.get("credits", 0)

            # 保存今日记录
            today_record = {
                "date": today,
                "credits": credits_now,
                "change": change_from_last
            }

            existing_idx = None
            for i, r in enumerate(records):
                if r.get("date") == today:
                    existing_idx = i
                    break

            if existing_idx is not None:
                records[existing_idx] = today_record
            else:
                records.append(today_record)

            # 保留指定天数的历史
            tz = pytz.timezone(settings.TZ)
            now = datetime.now(tz)
            keep = []
            for r in records:
                try:
                    dt_str = r.get('date', '')
                    if dt_str:
                        dt = datetime.strptime(dt_str, '%Y-%m-%d')
                        dt = tz.localize(dt) if dt.tzinfo is None else dt
                    else:
                        dt = now
                except Exception:
                    dt = now
                if (now - dt).days < self._history_days:
                    keep.append(r)

            data["records"] = keep
            data["username"] = info.get('username', self._username)
            data["uid"] = info.get('uid', self._uid)
            data["user_info"] = info

            # 计算统计
            stats = self._calculate_stats(keep)
            data["stats"] = stats

            self._save_data(data)

            # 生成报告
            report = self._generate_report(info, credits_now, change_from_last, today, stats)

            self._last_run_status = True
            self._last_run_message = report

            if self._notify:
                self.post_message(mtype="插件", title="绿联论坛积分查询", text=report)

            logger.info(f"积分查询完成: {credits_now} (变化: {change_from_last:+d})")
            return True, report

        except Exception as e:
            msg = f"❌ 积分查询异常: {str(e)}"
            self._last_run_status = False
            self._last_run_message = msg
            logger.error(msg)
            if self._notify:
                self.post_message(mtype="插件", title="绿联论坛积分查询", text=msg)
            return False, msg

    async def _auto_login(self) -> bool:
        """自动登录获取Cookie"""
        try:
            # 尝试 OAuth API 登录
            if await self._oauth_api_login():
                return True
        except Exception as e:
            logger.warning(f"OAuth API 登录失败: {e}")

        try:
            # 尝试 Playwright 登录
            if await self._playwright_login():
                return True
        except Exception as e:
            logger.warning(f"Playwright 登录失败: {e}")

        return False

    async def _oauth_api_login(self) -> bool:
        """OAuth API 自动登录"""
        try:
            from Crypto.Cipher import AES
            from Crypto.Util.Padding import pad

            headers_json = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
                'Accept': 'application/json, text/plain, */*',
                'Origin': 'https://web.ugnas.com',
                'Referer': 'https://web.ugnas.com/',
                'Accept-Language': 'zh-CN',
            }

            async with aiohttp.ClientSession() as session:
                # 1. 获取加密密钥
                async with session.get(
                    f'{self.API_BASE}/api/user/v3/sa/encrypt/key',
                    headers=headers_json,
                    timeout=aiohttp.ClientTimeout(total=self.REQUEST_TIMEOUT)
                ) as r1:
                    if r1.status != 200:
                        logger.warning(f"OAuth API 加密密钥获取失败: {r1.status}")
                        return False
                    data = await r1.json()

                api_data = data.get('data', {})
                encrypt_key = api_data.get('encryptKey')
                api_uuid = api_data.get('uuid')

                if not encrypt_key or not api_uuid:
                    logger.warning("OAuth API 未返回有效密钥")
                    return False

                # 2. AES 加密
                def aes_encrypt(text, key_str, iv_str):
                    key = key_str.encode('utf-8')
                    iv = iv_str[:16].encode('utf-8')
                    cipher = AES.new(key, AES.MODE_CBC, iv)
                    padded_data = pad(text.encode('utf-8'), AES.block_size)
                    encrypted = cipher.encrypt(padded_data)
                    return base64.b64encode(encrypted).decode('utf-8')

                try:
                    enc_user = aes_encrypt(self._username, encrypt_key, api_uuid)
                    enc_pwd = aes_encrypt(self._password, encrypt_key, api_uuid)
                except Exception as e:
                    logger.warning(f"OAuth API 加密失败: {e}")
                    return False

                # 3. 登录获取 Token
                form_headers = {
                    'User-Agent': headers_json['User-Agent'],
                    'Accept': 'application/json;charset=UTF-8',
                    'Origin': 'https://web.ugnas.com',
                    'Referer': 'https://web.ugnas.com/',
                    'Accept-Language': 'zh-CN',
                }

                req_bid = uuid.uuid4().hex
                files = {
                    'platform': (None, 'PC'),
                    'clientType': (None, 'browser'),
                    'osVer': (None, '142.0.0.0'),
                    'model': (None, 'Edge/142.0.0.0'),
                    'bid': (None, req_bid),
                    'alias': (None, 'Edge/142.0.0.0'),
                    'grant_type': (None, 'password'),
                    'username': (None, enc_user),
                    'password': (None, enc_pwd),
                    'uuid': (None, api_uuid),
                }

                async with session.post(
                    f'{self.API_BASE}/api/oauth/token',
                    headers=form_headers,
                    data=files,
                    timeout=aiohttp.ClientTimeout(total=self.REQUEST_TIMEOUT)
                ) as r2:
                    if r2.status != 200:
                        logger.warning(f"OAuth API 获取令牌失败: {r2.status}")
                        return False
                    tok = await r2.json()

                # 修复：支持多种 token 结构
                access_token = tok.get('access_token')
                if not access_token and isinstance(tok.get('data'), dict):
                    access_token = tok['data'].get('access_token')
                    if not access_token and isinstance(tok['data'].get('accessToken'), dict):
                        access_token = tok['data']['accessToken'].get('access_token')
                if notQ3�M4T4 =w۝܅��h���h���}���-jR�bC#��W6W&��R�C"�w&�W���7G&�����bW6W&��R��"�#��C2�&R�6V&6��"&6�73��&����U�#ⅵ��Ҳ���7��"��F���bC3��W6W&��R�C2�w&�W���7G&����W�6WBW�6WF��㠢70��2h�X�nzz�X�`�G'����&R�6V&6��"v6�73�&�֦�fV��֖6��#��7���B����7��zz�X�br��F���b�����G2���B��w&�W����V�6S��"�&R�6V&6��"~zz�X�e��ɣ���2���B��r��F���b#�����G2���B�"�w&�W�����b���G2�2���S��2�&R�6V&6��"v6�73�'�s%���ң�zz�X�c���B�����r��F���b3�����G2���B�2�w&�W����W�6WBW�6WF��㠢70��2h�X�nyJ�h�~{�@�G'���Vr�&R�6V&6��"s�Ɠ��V��yJ�h�~{�C��V��������ңⅵ��Ҳ����r��F���bVs��W6W&w&�W�Vr�w&�W���7G&����W�6WBW�6WF��㠢70��2h�X�nK���)�i[ �G'���F��&R�6V&6��"s�7���B����7��K���)�i[r��F���bF���F�&VG2���B�F��w&�W����W�6WBW�6WF��㠢70��2h�X�nY��[�ni[ �G'�����&R�6V&6��"s�7���B����7��Y��[�ni[r��F���b��7G2���B���w&�W����W�6WBW�6WF��㠢70��2h�X�nZ[�X��i[ �G'���g"�&R�6V&6��"s�7���B����7��Z[�X��i[r��F���bg#��g&�V�G2���B�g"�w&�W����W�6WBW�6WF��㠢70��2h�X�nZKNX8�G'���fF%��F6��&R�6V&6��"sƖ�u���Ҧ6�73�'W6W%�fF"%���ң�r��F���bfF%��F6�����u�Fr�fF%��F6��w&�W���7&5��F6��&R�6V&6��"w7&3�"���%Ҳ�"r���u�Fr���b7&5��F6���fF%�W&��7&5��F6��w&�W����br�fF"�r��fF%�W&��BfF%�W&��7F'G7v�F��v�GGr���fF"�fF%�W&��V�6S��fF"�fF%�W&���b��BfF#��fF"�&�GG3���&'2�6���72�Vv�2�6���&'2�fF"���fF"��r �W�6WBW�6WF��㠢fF"�&�GG3���&'2�6���72�Vv�2�6���&'2�fF"���fF"��r ����f����'V�B#�V�B�"6V�b��V�B��'W6W&��R#�W6W&��R��'���G2#����G2�"��&fF"#�fF"��'W6W&w&�W#�W6W&w&�W��'F�&VG2#�F�&VG2��'�7G2#��7G2��&g&�V�G2#�g&�V�G0�Р�6V�b�6fU�FF�v�7E�W6W%���f�r���f�&WGW&���f�FVb���E�FF�6V�b���F�7E�7G"��Ӡ�"".X����zz�X�nX�nX�.i[h��"" ��b6V�b��FF�f��R�B6V�b��FF�f��R�W��7G2����G'���v�F��V�6V�b��FF�f��R�'""�V�6�F��s�'WFbӂ"�2c��&WGW&��6�����B�b��W�6WBW�6WF���2S����vvW"�W'&�"�b.X����zz�X�ni[h��ZK�JS��W�"��&WGW&��'W6W&��R#�6V�b��W6W&��R�'V�B#�6V�b��V�B�'&V6�&G2#����'7FG2#����'W6W%���f�#���Р�FVb�6fU�FF�6V�b�FF�F�7E�7G"��Ғ�����S��"".K��Zَzz�X�nX�nX�.i[h��"" �G'����b6V�b��FF�f��S��6V�b��FF�f��R�&V�B�ֶF�"�&V�G3�G'VR�W��7E����G'VR��v�F��V�6V�b��FF�f��R�'r"�V�6�F��s�'WFbӂ"�2c���6���GV��FF�b���FV�C�"�V�7W&U�66���f�6R��W�6WBW�6WF���2S����vvW"�W'&�"�b.K��Zَzz�X�ni[h��ZK�JS��W�"���FVb�6�7V�FU�7FG2�6V�b�&V6�&G3�Ɨ7E�F�7E�7G"���Ғ��F�7E�7G"��Ӡ�"".��z�~zz�X�n{����"" ��b��B&V6�&G3��&WGW&��Р�7&VF�G5�Ɨ7B��"�vWB�&7&VF�G2"��f�""��&V6�&G5Т6��vU�Ɨ7B��"�vWB�&6��vR"��f�""��&V6�&G5Р�fƖE�7&VF�G2��2f�"2��7&VF�G5�Ɨ7B�b2�ТF�F��6��vR�7V҆6��vU�Ɨ7B���6�F�fU�F�2�7V҃f�"2��6��vU�Ɨ7B�b2����VvF�fU�F�2�7V҃f�"2��6��vU�Ɨ7B�b2����&WGW&���'F�F��&V6�&G2#��V�&V6�&G2���&���7&VF�G2#����fƖE�7&VF�G2��bfƖE�7&VF�G2V�6R��&֖��7&VF�G2#�֖�fƖE�7&VF�G2��bfƖE�7&VF�G2V�6R��&fu�7&VF�G2#�7V҇fƖE�7&VF�G2����V�fƖE�7&VF�G2��bfƖE�7&VF�G2V�6R��'F�F��6��vR#�F�F��6��vR��'�6�F�fU�F�2#��6�F�fU�F�2��&�VvF�fU�F�2#��VvF�fU�F�2��&7W'&V�E�7G&V�#�6V�b��6�7V�FU�7G&V��&V6�&G2���Р�FVb�6�7V�FU�7G&V��6V�b�&V6�&G3�Ɨ7E�F�7E�7G"���Ғ����C��"".��z�~���{��Z)�[�ZJ�i["" �7G&V�� �f�"&V6�&B��&WfW'6VB�&V6�&G2����b&V6�&B�vWB�&6��vR"�����7G&V����V�6S��'&V��&WGW&�7G&V���FVb�vV�W&FU�&W�'B��6V�b����f�F�7E�7G"�����7&VF�G5���s���B��6��vU�g&����7C���B��F�F��7G"��7FG3�F�7E�7G"��Т���7G#��"".yI�h�zz�X�nh�^Y�"" �6��vU�6�v��"�"�b6��vU�g&����7B��V�6R" ���R���f��vWB�wW6W&��Rr�6V�b��W6W&��R��V�B���f��vWB�wV�Br�6V�b��V�B��W6W&w&�W���f��vWB�wW6W&w&�Wr�rr���&W�'E�Ɩ�W2���b/	�8�{���N��Yپzz�X�niz^h�R"��b/	�ByJ�h�~�ɧ���W��T�C��V�GҒ"��Т�bW6W&w&�W��&W�'E�Ɩ�W2�V�B�b/	�RyJ�h�~{�N�ɧ�W6W&w&�W�"��&W�'E�Ɩ�W2�W�FV�B���b/	�8Riz^i���ɧ�F�F��"��b/	�+[�>X��zz�X�n�ɧ�7&VF�G5���w�"��b/	�8���>K��j��ɧ�6��vU�6�v�׶6��vU�g&����7G�"��Ґ���b7FG3���b7FG2�vWB�&7W'&V�E�7G&V�"�����&W�'E�Ɩ�W2�V�B�b/	�JR���{��Z)�[��ɧ�7FG5�v7W'&V�E�7G&V�u��ZJ�"���b7FG2�vWB�'�6�F�fU�F�2"���7FG2�vWB�&�VvF�fU�F�2"����&W�'E�Ɩ�W2�V�B�b/	�8�h�K�>�h�X���ɮK��kj���7FG5�w�6�F�fU�F�2u����7FG5�w�6�F�fU�F�2u��7FG5�v�VvF�fU�F�2u�Ғ"��VƖb7FG2�vWB�&�VvF�fU�F�2"���7FG2�vWB�'�6�F�fU�F�2"����&W�'E�Ɩ�W2�V�B�b/	�8�h�K�>�h�X���ɮK�����"���&WGW&�%��"����&W�'E�Ɩ�W2���FVbvWE�7FFR�6V�b���&��à�"".��~X�nh�.K�nx�nh"" ��b��B6V�b��V�&�VC��&WGW&�f�6P��b��B6V�b��6����R�B��B�6V�b��W6W&��R�B6V�b��77v�&B���&WGW&�f�6P�&WGW&�G'VP��7FF�6�WF��@�FVbvWE�6����B����Ɨ7C��&WGW&��Р�FVbvWE���6V�b���Ɨ7E�F�7E�7G"���Ӡ�&WGW&�����'F�#�"�&Vg&W6�"��&V�G���B#�6V�b����&Vg&W6���&�WF��G2#��%�5B%���'7V��'�#�.h��X��X�~ikzz�X�b"��&FW67&�F���#�.z��X�>h�~��K�j�zz�X�ni�^��" ������'F�#�"�7FG2"��&V�G���B#�6V�b����7FG2��&�WF��G2#��$tUB%���'7V��'�#�.��~X�n{����"��&FW67&�F���#�.��~X�nzz�X�n{����i[h�� �ТР�7��2FVb���&Vg&W6��6V�b���F�7E�7G"��Ӡ�""$��h��X��X�~ikzz�X�b"" �7V66W72��W76vR�v�B6V�b��F��F6��7��2���&WGW&��'7Vessage}

    def _api_stats(self) -> Dict[str, Any]:
        """API: 获取统计"""
        data = self._load_data()
        return {
            "success": True,
            "data": {
                "stats": data.get("stats", {}),
                "records_count": len(data.get("records", []))
            }
        }

    def get_form(self) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """插件配置表单"""
        return [
            {
                'component': 'VForm',
                'content': [
                    # 开关行
                    {
                        'component': 'VRow',
                        'content': [
                            {'component': 'VCol', 'props': {'cols': 12, 'md': 4}, 'content': [{'component': 'VSwitch', 'props': {'model': 'enabled', 'label': '启用插件'}}]},
                            {'component': 'VCol', 'props': {'cols': 12, 'md': 4}, 'content': [{'component': 'VSwitch', 'props': {'model': 'notify', 'label': '发送通知'}}]},
                            {'component': 'VCol', 'props': {'cols': 12, 'md': 4}, 'content': [{'component': 'VSwitch', 'props': {'model': 'onlyonce', 'label': '立即运行一次'}}]},
                        ]
                    },
                    # 提示信息
                    {
                        'component': 'VRow',
                        'content': [
                            {'component': 'VCol', 'props': {'cols': 12}, 'content': [
                                {'component': 'VAlert', 'props': {
                                    'type': 'info',
                                    'variant': 'tonal',
                                    'text': '💡 推荐：配置用户名和密码后可自动登录刷新Cookie。也可手动获取Cookie填入下方。'
                                }}
                            ]}
                        ]
                    },
                    # 账号密码
                    {
                        'component': 'VRow',
                        'content': [
                            {'component': 'VCol', 'props': {'cols': 12, 'md': 6}, 'content': [{'component': 'VTextField', 'props': {'model': 'username', 'label': '用户名/手机号', 'placeholder': '用于自动登录'}}]},
                            {'component': 'VCol', 'props': {'cols': 12, 'md': 6}, 'content': [{'component': 'VTextField', 'props': {'model': 'password', 'label': '密码', 'type': 'password', 'placeholder': '用于自动登录'}}]},
                        ]
                    },
                    # Cookie
                    {
                        'component': 'VRow',
                        'content': [
                            {'component': 'VCol', 'props': {'cols': 12}, 'content': [{'component': 'VTextarea', 'props': {'model': 'cookie', 'label': '论坛Cookie（可选，自动登录会自动获取）', 'placeholder': '6LQh_2132_auth=...; 其它...', 'rows': 3}}]},
                        ]
                    },
                    # 定时和UID
                    {
                        'component': 'VRow',
                        'content': [
                            {'component': 'VCol', 'props': {'cols': 12, 'md': 4}, 'content': [{'component': 'VCronField', 'props': {'model': 'cron', 'label': '定时规则'}}]},
                            {'component': 'VCol', 'props': {'cols': 12, 'md': 4}, 'content': [{'component': 'VTextField', 'props': {'model': 'uid', 'label': '用户UID（可选，自动获取）', 'placeholder': '留空自动获取'}}]},
                            {'component': 'VCol', 'props': {'cols': 12, 'md': 4}, 'content': [{'component': 'VTextField', 'props': {'model': 'history_days', 'label': '历史保留天数', 'type': 'number', 'placeholder': '30'}}]},
                        ]
                    },
                    # 重试和超时
                    {
                        'component': 'VRow',
                        'content': [
                            {'component': 'VCol', 'props': {'cols': 12, 'md': 6}, 'content': [{'component': 'VTextField', 'props': {'model': 'retry_times', 'label': '重试次数', 'type': 'number', 'min': 1, 'max': 10}}]},
                            {'component': 'VCol', 'props': {'cols': 12, 'md': 6}, 'content': [{'component': 'VTextField', 'props': {'model': 'timeout', 'label': '超时时间(秒)', 'type': 'number', 'min': 10, 'max': 120}}]},
                        ]
                    },
                ]
            }
        ], {
            "enabled": False,
            "onlyonce": False,
            "cron": "0 8 * * *",
            "cookie": "",
            "username": "",
            "password": "",
            "uid": "",
            "notify": True,
            "retry_times": 3,
            "retry_delay": 2,
            "timeout": 30,
            "history_days": 30,
        }

    def get_page(self) -> List[Dict[str, Any]]:
        """插件详情页面"""
        data = self._load_data()
        records = data.get("records", [])
        user_info = data.get("user_info", {})
        stats = data.get("stats", {})

        # 空状态处理
        if not records:
            return [
                {'component': 'VAlert', 'props': {'type': 'info', 'variant': 'tonal', 'text': '暂无积分记录，请先配置Cookie或账号密码并启用插件'}}
            ]

        # 用户信息卡片
        card = []
        if user_info:
            name = user_info.get('username', '-')
            avatar = user_info.get('avatar')
            points = user_info.get('points', 0)
            usergroup = user_info.get('usergroup', '')
            threads = user_info.get('threads', 0)
            posts = user_info.get('posts', 0)
            friends = user_info.get('friends', 0)
            uid_val = user_info.get('uid', '')

            latest = records[-1] if records else {}
            latest_change = latest.get('change', 0)
            latest_date = latest.get('date', '-')
            latest_color = 'success' if latest_change > 0 else ('grey' if latest_change == 0 else 'error')
            latest_emoji = '📈' if latest_change > 0 else ('➖' if latest_change == 0 else '📉')

            card = [
                {
                    'component': 'VCard',
                    'props': {'variant': 'elevated', 'elevation': 2, 'rounded': 'lg', 'class': 'mb-4'},
                    'content': [
                        {'component': 'VCardTitle', 'props': {'class': 'text-h5 font-weight-bold'}, 'text': '👤 绿联论坛用户信息'},
                        {'component': 'VCardText', 'content': [
                            {'component': 'VRow', 'props': {'align': 'center'}, 'content': [
                                {'component': 'VCol', 'props': {'cols': 12, 'md': 2}, 'content': [
                                    ({'component': 'VAvatar', 'props': {'size': 96, 'class': 'mx-auto'}, 'content': [{'component': 'VImg', 'props': {'src': avatar}}]} if avatar else {'component': 'VAvatar', 'props': {'size': 96, 'color': 'grey-lighten-2', 'class': 'mx-auto'}, 'text': name[:1] if name else '?'})
                                ]},
                                {'component': 'VCol', 'props': {'cols': 12, 'md': 10}, 'content': [
                                    {'component': 'VRow', 'props': {'class': 'mb-3'}, 'content': [
                                        {'component': 'VCol', 'props': {'cols': 12}, 'content': [
                                            {'component': 'div', 'props': {'class': 'text-h5 font-weight-bold'}, 'text': name},
                                            {'component': 'div', 'props': {'class': 'text-subtitle-2 text-medium-emphasis mt-1'}, 'text': f"🆔 UID: {uid_val}" + (f" | 👥 {usergroup}" if usergroup else "")}
                                        ]}
                                    ]},
                                    {'component': 'VRow', 'content': [
                                        {'component': 'VCol', 'props': {'cols': 6, 'sm': 3}, 'content': [
                                            {'component': 'VChip', 'props': {'size': 'large', 'variant': 'tonal', 'class': 'ma-1', 'color': 'amber-darken-2'}, 'text': f'💰 积分 {points}'}
                                        ]},
                                        {'component': 'VCol', 'props': {'cols': 6, 'sm': 3}, 'content': [
                                            {'component': 'VChip', 'props': {'size': 'large', 'variant': 'tonal', 'class': 'ma-1', 'color': 'blue'}, 'text': f'📝 主题 {threads}'}
                                        ]},
                                        {'component': 'VCol', 'props': {'cols': 6, 'sm': 3}, 'content': [
                                            {'component': 'VChip', 'props': {'size': 'large', 'variant': 'tonal', 'class': 'ma-1', 'color': 'green'}, 'text': f'💬 回帖 {posts}'}
                                        ]},
                                        {'component': 'VCol', 'props': {'cols': 6, 'sm': 3}, 'content': [
                                            {'component': 'VChip', 'props': {'size': 'large', 'variant': 'tonal', 'class': 'ma-1', 'color': 'purple'}, 'text': f'👥 好友 {friends}'}
                                        ]}
                                    ]}
                                ]},
                                {'component': 'VCol', 'props': {'cols': 12}, 'content': [
                                    {'component': 'VDivider'},
                                    {'component': 'VRow', 'props': {'class': 'mt-3'}, 'content': [
                                        {'component': 'VCol', 'props': {'cols': 12, 'md': 4}, 'content': [
                                            {'component': 'VChip', 'props': {'size': 'default', 'variant': 'elevated', 'color': latest_color}, 'text': f'最近变化 {latest_emoji} {"+" if latest_change > 0 else ""}{latest_change}'}
                                        ]},
                                        {'component': 'VCol', 'props': {'cols': 12, 'md': 4}, 'content': [
                                            {'component': 'VChip', 'props': {'size': 'default', 'variant': 'tonal'}, 'text': f'更新时间 {latest_date}'}
                                        ]}
                                    ]}
                                ]}
                            ]}
                        ]}
                    ]
                }
            ]

        # 统计卡片
        stat_cards = []
        if stats:
            stat_items = [
                ("总记录", f"{stats.get('total_records', 0)} 天", "primary"),
                ("最高积分", f"{stats.get('max_credits', 0)}", "success"),
                ("增长天数", f"{stats.get('positive_days', 0)} 天", "info"),
                ("连续增长", f"{stats.get('current_streak', 0)} 天", "warning"),
            ]
            for title, value, color in stat_items:
                stat_cards.append({
                    'component': 'VCard',
                    'props': {'variant': 'outlined', 'class': 'text-center'},
                    'content': [
                        {'component': 'VCardText', 'content': [
                            {'component': 'div', 'props': {'class': 'text-h6', 'text': value}},
                            {'component': 'div', 'props': {'class': 'text-caption text-grey', 'text': title}}
                        ]}
                    ]
                })

        # 历史记录表格
        rows = []
        for record in reversed(records[-30:]):
            change = record.get("change", 0)
            change_text = f"+{change}" if change > 0 else str(change)
            change_color = "success" if change > 0 else ("error" if change < 0 else "grey")

            rows.append({
                'component': 'tr',
                'content': [
                    {'component': 'td', 'text': record.get("date", "")},
                    {'component': 'td', 'text': record.get("credits", 0)},
                    {'component': 'td', 'class': f'text-{change_color}', 'text': change_text}
                ]
            })

        return card + [
            {'component': 'VRow', 'content': [
                {'component': 'VCol', 'props': {'cols': 12, 'md': 3}, 'content': [card_item]} if stat_cards else {'component': 'div'}
                for card_item in stat_cards
            ]} if stat_cards else {'component': 'div'},
            {
                'component': 'VCard',
                'props': {'variant': 'outlined', 'class': 'mt-4'},
                'content': [
                    {'component': 'VCardTitle', 'text': f'📜 积分历史 (近{len(rows)}条)'},
                    {
                        'component': 'VCardText',
                        'content': [{
                            'component': 'VTable',
                            'props': {'density': 'compact'},
                            'content': [{
                                'component': 'thead',
                                'content': [{'component': 'tr', 'content': [
                                    {'component': 'th', 'text': '日期'},
                                    {'component': 'th', 'text': '积分'},
                                    {'component': 'th', 'text': '变化'}
                                ]}]
                            }, {
                                'component': 'tbody',
                                'content': rows
                            }]
                        }]
                    }
                ]
            }
        ]

    def stop_service(self) -> None:
        """停止插件服务"""
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None
            logger.info("绿联论坛积分查询定时任务已停止")
