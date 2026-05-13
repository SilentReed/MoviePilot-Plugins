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

    plugin_name: str = "绿联论坛积分查询"
    plugin_desc: str = "每日定时查询绿联论坛积分变化并推送通知，支持自动登录"
    plugin_icon: str = "icons/ugnascredits.svg"
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
        self.stop_service()

        self._data_file: Path = Path(settings.ROOT_PATH) / "plugins" / "data" / "ugnascredits" / "credits.json"

        # 默认值
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
                if not access_token:
                    logger.warning("OAuth API 未返回有效令牌")
                    return False

                # 4. 授权回调
                state = uuid.uuid4().hex[:12]
                authorize_url = (
                    f'{self.API_BASE}/api/oauth/authorize?response_type=code&client_id=discuz-client&scope=user_info'
                    f'&state={state}&redirect_uri={quote("https://club.ugnas.com/api/ugreen/callback.php")}&access_token={access_token}'
                )

                async with session.get(
                    authorize_url,
                    headers=headers_json,
                    allow_redirects=False,
                    timeout=aiohttp.ClientTimeout(total=self.REQUEST_TIMEOUT)
                ) as r3:
                    loc = r3.headers.get('location') or r3.headers.get('Location')

                if not loc:
                    logger.warning("OAuth API 未获取回调地址")
                    return False

                # 5. 访问回调地址设置Cookie
                callback_headers = {
                    'User-Agent': headers_json['User-Agent'],
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'zh-CN'
                }
                async with session.get(loc, headers=callback_headers, timeout=aiohttp.ClientTimeout(total=self.REQUEST_TIMEOUT)) as r4:
                    pass

                # 刷新站点首页
                async with session.get(
                    f'{self.BASE_URL}/',
                    headers=callback_headers,
                    timeout=aiohttp.ClientTimeout(total=self.REQUEST_TIMEOUT)
                ) as r5:
                    pass

                # 汇总Cookie
                cookie_items = []
                for c in session.cookie_jar:
                    cookie_items.append(f"{c.name}={c.value}")

                if cookie_items:
                    ck = '; '.join(cookie_items)
                    if '6LQh_2132_BBRules_ok=' not in ck:
                        ck += '; 6LQh_2132_BBRules_ok=1'
                    self._cookie = ck
                    self._save_config()
                    has_auth = ('6LQh_2132_auth=' in ck)
                    return has_auth

            return False
        except Exception as e:
            logger.warning(f"OAuth API 登录异常: {e}")
            return False

    async def _playwright_login(self) -> bool:
        """Playwright 浏览器登录"""
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                ctx = await browser.new_context()
                page = await ctx.new_page()

                await page.goto(f"{self.BASE_URL}/", wait_until="domcontentloaded")

                # 点击同意按钮
                try:
                    btn = page.locator("button:has-text('同意')")
                    if await btn.count() > 0:
                        await btn.first.click()
                        await page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass

                # 设置BBRules cookie
                try:
                    await ctx.add_cookies([{
                        "name": "6LQh_2132_BBRules_ok",
                        "value": "1",
                        "domain": "club.ugnas.com",
                        "path": "/",
                        "secure": True,
                        "httpOnly": False,
                        "expires": int(time.time()) + 31536000
                    }])
                except Exception:
                    pass

                # 访问登录页
                await page.goto(f"{self.BASE_URL}/member.php?mod=logging&action=login", wait_until="domcontentloaded")

                # 填写用户名密码
                u_sels = ["input[name='username']", "input[id='username']", "input[type='text']"]
                p_sels = ["input[name='password']", "input[id='password']", "input[type='password']"]

                for s in u_sels:
                    if await page.query_selector(s):
                        await page.fill(s, self._username)
                        break

                for s in p_sels:
                    if await page.query_selector(s):
                        await page.fill(s, self._password)
                        break

                # 点击登录
                btn = await page.query_selector("button[type='submit']") or await page.query_selector("input[type='submit']")
                if btn:
                    await btn.click()
                else:
                    await page.keyboard.press("Enter")

                try:
                    await page.wait_for_load_state("networkidle", timeout=12000)
                except Exception:
                    pass

                # 刷新首页
                try:
                    await page.goto(f"{self.BASE_URL}/", wait_until="domcontentloaded")
                    await page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass

                # 获取Cookie
                cookies = await ctx.cookies()
                parts = []
                for c in cookies:
                    n, v = c.get('name'), c.get('value')
                    if n and v:
                        parts.append(f"{n}={v}")

                await ctx.close()
                await browser.close()

                if parts:
                    self._cookie = "; ".join(parts)
                    if '6LQh_2132_BBRules_ok=' not in self._cookie:
                        self._cookie += "; 6LQh_2132_BBRules_ok=1"
                    has_auth = any('6LQh_2132_auth=' in p for p in parts)
                    if has_auth:
                        self._save_config()
                        return True

            return False
        except Exception as e:
            logger.warning(f"Playwright 登录异常: {e}")
            return False

    async def _fetch_user_profile(self) -> Optional[Dict[str, Any]]:
        """获取用户资料和积分"""
        if not self._cookie:
            return None

        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Cookie': self._cookie
        }

        try:
            async with aiohttp.ClientSession() as session:
                # 尝试获取UID
                uid = self._uid
                if not uid:
                    uid = await self._discover_uid(session, headers)

                if uid:
                    url = f'{self.BASE_URL}/home.php?mod=space&uid={uid}'
                else:
                    url = f'{self.BASE_URL}/forum.php?mod=forumdisplay&fid=0'

                async with session.get(
                    url,
                    headers=headers,
                    ssl=False,
                    timeout=aiohttp.ClientTimeout(total=self._timeout)
                ) as resp:
                    if resp.status != 200:
                        return None
                    html = await resp.text()

                # 解析用户信息
                info = self._parse_user_info(html, uid)
                if info:
                    self.save_data('last_user_info', info)
                return info

        except Exception as e:
            logger.error(f"获取用户资料失败: {e}")
            return None

    async def _discover_uid(self, session, headers) -> Optional[str]:
        """发现用户UID"""
        urls = [
            f'{self.BASE_URL}/forum.php?mod=forumdisplay&fid=0',
            f'{self.BASE_URL}/home.php',
        ]
        for u in urls:
            try:
                async with session.get(
                    u,
                    headers=headers,
                    ssl=False,
                    timeout=aiohttp.ClientTimeout(total=self._timeout)
                ) as resp:
                    html = await resp.text()

                # 尝试多种方式提取UID
                patterns = [
                    r'id="comiis_user"[\s\S]*?href="home\.php\?mod=space(?:&|&amp;)uid=(\d+)"',
                    r'discuz_uid\s*=\s*\'?(\d+)\'?',
                    r'home\.php\?mod=space(?:&|&amp;)uid=(\d+)',
                ]

                for pattern in patterns:
                    match = re.search(pattern, html)
                    if match and match.group(1) != '0':
                        return match.group(1)
            except Exception:
                continue

        return None

    def _parse_user_info(self, html: str, uid: Optional[str]) -> Optional[Dict[str, Any]]:
        """解析HTML获取用户信息"""
        if not html:
            return None

        username = self._username or "-"
        points = None
        avatar = None
        usergroup = None
        threads = 0
        posts = 0
        friends = 0

        # 提取用户名
        try:
            t = re.search(r"<li><em>用户名</em>([^<]+)</li>", html)
            if t:
                username = t.group(1).strip()
            else:
                t2 = re.search(r"<h2 class=\"mbn\">基本资料</h2>[\s\S]*?<li><em>用户名</em>([^<]+)</li>", html)
                if t2:
                    username = t2.group(1).strip()
            if username == "-":
                t3 = re.search(r"class=\"kmname\">([^<]+)</span>", html)
                if t3:
                    username = t3.group(1).strip()
        except Exception:
            pass

        # 提取积分
        try:
            p = re.search(r'class="kmjifen kmico09"><span>(\d+)</span>积分', html)
            if p:
                points = int(p.group(1))
            else:
                p2 = re.search(r'积分[：:]\s*(\d+)', html)
                if p2:
                    points = int(p2.group(1))
            if points is None:
                p3 = re.search(r'class="xg1"[^>]*>积分: (\d+)</a>', html)
                if p3:
                    points = int(p3.group(1))
        except Exception:
            pass

        # 提取用户组
        try:
            ug = re.search(r'<li><em>用户组</em>.*?<a[^>]*>([^<]+)</a>', html)
            if ug:
                usergroup = ug.group(1).strip()
        except Exception:
            pass

        # 提取主题数
        try:
            th = re.search(r'<span>(\d+)</span>主题数', html)
            if th:
                threads = int(th.group(1))
        except Exception:
            pass

        # 提取回帖数
        try:
            po = re.search(r'<span>(\d+)</span>回帖数', html)
            if po:
                posts = int(po.group(1))
        except Exception:
            pass

        # 提取好友数
        try:
            fr = re.search(r'<span>(\d+)</span>好友数', html)
            if fr:
                friends = int(fr.group(1))
        except Exception:
            pass

        # 提取头像
        try:
            avatar_match = re.search(r'<img[^>]*class="user_avatar"[^>]*>', html)
            if avatar_match:
                img_tag = avatar_match.group(0)
                src_match = re.search(r'src="([^"]+)"', img_tag)
                if src_match:
                    avatar_url = src_match.group(1)
                    if '/avatar/' in avatar_url and avatar_url.startswith('http'):
                        avatar = avatar_url
                    else:
                        avatar = avatar_url
            if not avatar:
                avatar = "https://bbs-cn-oss.ugnas.com/bbs/avatar/noavatar.png"
        except Exception:
            avatar = "https://bbs-cn-oss.ugnas.com/bbs/avatar/noavatar.png"

        info = {
            "uid": uid or self._uid,
            "username": username,
            "points": points or 0,
            "avatar": avatar,
            "usergroup": usergroup,
            "threads": threads,
            "posts": posts,
            "friends": friends
        }

        self.save_data('last_user_info', info)
        return info

    def _load_data(self) -> Dict[str, Any]:
        """加载积分历史数据"""
        if self._data_file and self._data_file.exists():
            try:
                with open(self._data_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载积分数据失败: {e}")
        return {"username": self._username, "uid": self._uid, "records": [], "stats": {}, "user_info": {}}

    def _save_data(self, data: Dict[str, Any]) -> None:
        """保存积分历史数据"""
        try:
            if self._data_file:
                self._data_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self._data_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存积分数据失败: {e}")

    def _calculate_stats(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """计算积分统计"""
        if not records:
            return {}

        credits_list = [r.get("credits", 0) for r in records]
        change_list = [r.get("change", 0) for r in records]

        valid_credits = [c for c in credits_list if c > 0]
        total_change = sum(change_list)
        positive_days = sum(1 for c in change_list if c > 0)
        negative_days = sum(1 for c in change_list if c < 0)

        return {
            "total_records": len(records),
            "max_credits": max(valid_credits) if valid_credits else 0,
            "min_credits": min(valid_credits) if valid_credits else 0,
            "avg_credits": sum(valid_credits) // len(valid_credits) if valid_credits else 0,
            "total_change": total_change,
            "positive_days": positive_days,
            "negative_days": negative_days,
            "current_streak": self._calculate_streak(records),
        }

    def _calculate_streak(self, records: List[Dict[str, Any]]) -> int:
        """计算连续增长天数"""
        streak = 0
        for record in reversed(records):
            if record.get("change", 0) > 0:
                streak += 1
            else:
                break
        return streak

    def _generate_report(
        self,
        info: Dict[str, Any],
        credits_now: int,
        change_from_last: int,
        today: str,
        stats: Dict[str, Any]
    ) -> str:
        """生成积分报告"""
        change_sign = "+" if change_from_last >= 0 else ""
        name = info.get('username', self._username)
        uid = info.get('uid', self._uid)
        usergroup = info.get('usergroup', '')

        report_lines = [
            f"📊 绿联论坛积分日报",
            f"👤 用户：{name} (UID: {uid})",
        ]
        if usergroup:
            report_lines.append(f"👥 用户组：{usergroup}")
        report_lines.extend([
            f"📅 日期：{today}",
            f"💰 当前积分：{credits_now}",
            f"📈 较上次：{change_sign}{change_from_last}",
        ])

        if stats:
            if stats.get("current_streak", 0) > 0:
                report_lines.append(f"🔥 连续增长：{stats['current_streak']} 天")
            if stats.get("positive_days", 0) > stats.get("negative_days", 0):
                report_lines.append(f"📈 总体趋势：上涨 ({stats['positive_days']}/{stats['positive_days'] + stats['negative_days']})")
            elif stats.get("negative_days", 0) > stats.get("positive_days", 0):
                report_lines.append(f"📉 总体趋势：下降")

        return "\n".join(report_lines)

    def get_state(self) -> bool:
        """获取插件状态"""
        if not self._enabled:
            return False
        if not self._cookie and not (self._username and self._password):
            return False
        return True

    @staticmethod
    def get_command() -> List:
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {
                "path": "/refresh",
                "endpoint": self._api_refresh,
                "methods": ["POST"],
                "summary": "手动刷新积分",
                "description": "立即执行一次积分查询"
            },
            {
                "path": "/stats",
                "endpoint": self._api_stats,
                "methods": ["GET"],
                "summary": "获取统计",
                "description": "获取积分统计数据"
            }
        ]

    async def _api_refresh(self) -> Dict[str, Any]:
        """API: 手动刷新积分"""
        success, message = await self._do_task_async()
        return {"success": success, "message": message}

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
