"""
MCSManager 服务器状态查询 AstrBot 插件主体
CPU/内存通过 overview API 获取节点系统级数据
"""

import os
import io
import json
import hashlib
import tempfile
import aiohttp
from typing import Optional, List, Tuple, Set
from datetime import datetime

from astrbot.api.star import Star, Context, register
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api import logger

from .api import McsmApiClient
from .draw import render_dashboard

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# -----------------------------------------------
#  常量
# -----------------------------------------------

STATUS_MAP = {
    -1: "❓ 未知",
    0: "🔴 已停止",
    1: "🟡 停止中",
    2: "🟡 启动中",
    3: "🟢 运行中",
}

HELP_TEXT = """MCSManager 服务器管理
─────────────────────
/mcsm status [名称]       查看状态
/mcsm list                列出所有实例
/mcsm start [名称/序号]    启动服务器
/mcsm stop [名称/序号]     停止服务器
/mcsm restart [名称/序号]  重启服务器
/mcsm kill [名称/序号]     强制终止
/mcsm cmd [实例名] <命令>  发送控制台命令
/mcsm say <内容>          向服务器发送 say 广播
/mcsm panel [序号]         状态面板（图片）
/mcsm help                帮助信息

💡 背景图推荐尺寸: 680×400 像素
💡 可在 backgrounds/ 目录放入本地背景图"""

BG_CACHE_PREFIX = "bg_cache_"


# -----------------------------------------------
#  辅助函数
# -----------------------------------------------

def _safe_list(val) -> list:
    if val is None:
        return []
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def _url_to_cache_name(url: str) -> str:
    url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()[:12]
    lower = url.lower().split("?")[0].split("#")[0]
    ext = ".png"
    for e in (".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".png"):
        if lower.endswith(e):
            ext = e
            break
    return f"{BG_CACHE_PREFIX}{url_hash}{ext}"


def _get_sender_id(event: AstrMessageEvent) -> str:
    if hasattr(event, "get_sender_id"):
        return str(event.get_sender_id() or "").strip()
    if hasattr(event, "sender_id"):
        return str(event.sender_id or "").strip()
    if hasattr(event, "get_sender"):
        sender = event.get_sender()
        if hasattr(sender, "user_id"):
            return str(sender.user_id or "").strip()
    return ""


def _get_group_id(event: AstrMessageEvent) -> str:
    if hasattr(event, "get_group_id"):
        return str(event.get_group_id() or "").strip()
    if hasattr(event, "group_id"):
        return str(event.group_id or "").strip()
    if hasattr(event, "get_group"):
        grp = event.get_group()
        if hasattr(grp, "group_id"):
            return str(grp.group_id or "").strip()
    return ""


def _format_bytes(n: int) -> str:
    if not n or n <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = 0
    val = float(n)
    while val >= 1024 and idx < len(units) - 1:
        val /= 1024
        idx += 1
    if idx >= 2:
        return f"{val:.1f} {units[idx]}"
    return f"{val:.0f} {units[idx]}"


def _format_uptime(seconds: float) -> str:
    if not seconds or seconds <= 0:
        return "-"
    seconds = int(seconds)
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, _ = divmod(rem, 60)
    parts = []
    if d > 0:
        parts.append(f"{d}天")
    if h > 0:
        parts.append(f"{h}时")
    parts.append(f"{m}分")
    return " ".join(parts)


# -----------------------------------------------
#  插件主体
# -----------------------------------------------

@register(
    "astrbot-plugin-mcsm-status",
    "xiaotang666",
    "MCSManager 服务器状态查询插件",
    "1.9.0",
    "https://github.com/xiaotang666/astrbot_plugin_mcsm-status",
)
class McsmStatusPlugin(Star):

    def __init__(self, context: Context, config: dict):
        try:
            if isinstance(config, str):
                config = json.loads(config)
            if not isinstance(config, dict):
                config = {}
        except Exception:
            config = {}

        super().__init__(context, config)

        self.base_url: str = str(config.get("base_url", "http://127.0.0.1:23333")).rstrip("/")
        self.api_key: str = str(config.get("api_key", ""))
        self.timeout: int = int(config.get("timeout", 10) or 10)

        self.api = McsmApiClient(self.base_url, self.api_key, self.timeout)

        self.super_admin_ids: List[str] = [
            str(x).strip() for x in _safe_list(config.get("super_admin_ids")) if str(x).strip()
        ]
        self.admin_ids: List[str] = [
            str(x).strip() for x in _safe_list(config.get("admin_ids")) if str(x).strip()
        ]
        self.member_ids: List[str] = [
            str(x).strip() for x in _safe_list(config.get("member_ids")) if str(x).strip()
        ]

        _raw_admin = _safe_list(config.get("admin_commands"))
        self.admin_commands: Set[str] = set(
            str(x).strip() for x in _raw_admin if str(x).strip()
        ) if _raw_admin else {
            "status", "list", "start", "stop", "restart", "kill", "cmd", "say", "panel", "help"
        }

        _raw_member = _safe_list(config.get("member_commands"))
        self.member_commands: Set[str] = set(
            str(x).strip() for x in _raw_member if str(x).strip()
        ) if _raw_member else {"status", "list", "panel", "help"}

        self.group_whitelist: List[str] = [
            str(x).strip() for x in _safe_list(config.get("group_whitelist")) if str(x).strip()
        ]

        self.bg_urls: List[str] = [
            str(x).strip() for x in _safe_list(config.get("background_urls")) if str(x).strip()
        ]
        self._bg_dir: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backgrounds")
        os.makedirs(self._bg_dir, exist_ok=True)
        self._sync_bg_cache()

        self._bg_index: int = 0
        self._bg_current_key: Optional[str] = None
        self._bg_current_img = None

    # ==========================================
    #  背景图缓存
    # ==========================================

    def _get_cache_path(self, url: str) -> str:
        return os.path.join(self._bg_dir, _url_to_cache_name(url))

    def _sync_bg_cache(self):
        if not os.path.isdir(self._bg_dir):
            return
        valid_names = set(_url_to_cache_name(url) for url in self.bg_urls)
        for fname in os.listdir(self._bg_dir):
            if fname.startswith(BG_CACHE_PREFIX) and fname not in valid_names:
                try:
                    os.remove(os.path.join(self._bg_dir, fname))
                except Exception as e:
                    logger.warning(f"MCSM: 删除缓存失败 ({fname}): {e}")

    def _read_cache(self, url: str) -> Optional[bytes]:
        cache_path = self._get_cache_path(url)
        if os.path.isfile(cache_path):
            try:
                with open(cache_path, "rb") as f:
                    return f.read()
            except Exception:
                return None
        return None

    def _write_cache(self, url: str, data: bytes):
        try:
            with open(self._get_cache_path(url), "wb") as f:
                f.write(data)
        except Exception as e:
            logger.warning(f"MCSM: 写入缓存失败: {e}")

    async def _load_background(self, url: str):
        if not HAS_PIL:
            return None
        img_data = self._read_cache(url)
        if img_data is None:
            try:
                session = await self.api._ensure_session()
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        img_data = await resp.read()
                        self._write_cache(url, img_data)
                    else:
                        return None
            except Exception:
                return None
        try:
            img = Image.open(io.BytesIO(img_data))
            img.load()
            return img
        except Exception:
            return None

    def _scan_local_backgrounds(self) -> list:
        if not os.path.isdir(self._bg_dir):
            return []
        exts = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
        local_files = []
        for fname in sorted(os.listdir(self._bg_dir)):
            if fname.startswith(BG_CACHE_PREFIX):
                continue
            ext = os.path.splitext(fname)[1].lower()
            if ext in exts:
                local_files.append(os.path.join(self._bg_dir, fname))
        return local_files

    def _load_local_image(self, file_path: str):
        if not HAS_PIL:
            return None
        try:
            img = Image.open(file_path)
            img.load()
            return img
        except Exception:
            return None

    async def _get_background(self):
        if not HAS_PIL:
            return None
        if self.bg_urls:
            url = self.bg_urls[self._bg_index % len(self.bg_urls)]
            self._bg_index = (self._bg_index + 1) % len(self.bg_urls)
            if url == self._bg_current_key and self._bg_current_img is not None:
                return self._bg_current_img
            img = await self._load_background(url)
            self._bg_current_key = url if img else None
            self._bg_current_img = img
            return img
        local_files = self._scan_local_backgrounds()
        if not local_files:
            return None
        file_path = local_files[self._bg_index % len(local_files)]
        self._bg_index = (self._bg_index + 1) % len(local_files)
        if file_path == self._bg_current_key and self._bg_current_img is not None:
            return self._bg_current_img
        img = self._load_local_image(file_path)
        self._bg_current_key = file_path if img else None
        self._bg_current_img = img
        return img

    # ==========================================
    #  权限检查
    # ==========================================

    def _is_permission_enabled(self) -> bool:
        return bool(self.super_admin_ids or self.admin_ids or self.member_ids)

    def _check_group_whitelist(self, event: AstrMessageEvent) -> bool:
        if not self.group_whitelist:
            return True
        group_id = _get_group_id(event)
        if not group_id:
            return True
        return group_id in self.group_whitelist

    def _get_user_role(self, sender_id: str) -> str:
        if sender_id in self.super_admin_ids:
            return "super_admin"
        if sender_id in self.admin_ids:
            return "admin"
        if sender_id in self.member_ids:
            return "member"
        return "guest"

    def _check_permission(self, sender_id: str, cmd: str) -> Tuple[bool, str]:
        if cmd == "help":
            return (True, "")
        if not self._is_permission_enabled():
            return (True, "")
        role = self._get_user_role(sender_id)
        if role == "super_admin":
            return (True, "")
        if role == "admin":
            if cmd in self.admin_commands:
                return (True, "")
            return (False, f"❌ 权限不足（管理员无法使用 {cmd} 命令）")
        if role == "member":
            if cmd in self.member_commands:
                return (True, "")
            return (False, f"❌ 权限不足（成员无法使用 {cmd} 命令）")
        return (False, "❌ 权限不足，请联系管理员添加白名单")

    def _pre_check(self, event: AstrMessageEvent, cmd: str) -> Optional[str]:
        if not self.api_key:
            return "❌ 请先在插件配置中填写 MCSManager API Key"
        if not self._check_group_whitelist(event):
            return ""
        sender_id = _get_sender_id(event)
        allowed, reason = self._check_permission(sender_id, cmd)
        if not allowed:
            return reason
        return None

    # ==========================================
    #  格式化输出
    # ==========================================

    def fmt_detail(self, inst: dict, d_label: str, d_uuid: str) -> str:
        if not isinstance(inst, dict):
            return "❌ 实例数据格式异常"

        cfg = inst.get("config", {})
        if not isinstance(cfg, dict):
            cfg = {}
        info = inst.get("info", {})
        if not isinstance(info, dict):
            info = {}

        daemon_stat = self.api.get_daemon_stats(d_uuid)

        name = cfg.get("nickname", inst.get("instanceUuid", "未知"))
        status = inst.get("status", -1)
        lines = [
            "┌───────────────────────",
            f"│ 🖥️  {name}",
            f"│ 状态: {STATUS_MAP.get(status, '❓ 未知')}",
        ]

        if status == 3:
            version = info.get("version", "")
            if version:
                lines.append(f"│ 📦 版本: {version}")

            current = info.get("currentPlayers", 0)
            max_p = info.get("maxPlayers", "?")
            lines.append(f"│ 👥 玩家: {current}/{max_p}")

            cpu = daemon_stat.get("cpu", 0)
            if cpu > 0:
                lines.append(f"│ 💻 CPU: {cpu:.1f}%")
            else:
                lines.append("│ 💻 CPU: -")

            mem_used = daemon_stat.get("mem_used", 0)
            mem_total = daemon_stat.get("mem_total", 0)
            if mem_total > 0:
                used_mb = mem_used / 1024 / 1024
                total_mb = mem_total / 1024 / 1024
                lines.append(f"│ 🧠 内存: {used_mb:.0f}/{total_mb:.0f} MB")
            else:
                lines.append("│ 🧠 内存: -")

            latency = info.get("latency", 0)
            if latency:
                lines.append(f"│ 📡 延迟: {latency}ms")

        port = cfg.get("basePort") or cfg.get("port")
        if port:
            lines.append(f"│ 🌐 端口: {port}")

        node_name = daemon_stat.get("hostname", "") or d_label
        if node_name:
            lines.append(f"│ 🖧 节点: {node_name}")

        node_uptime = daemon_stat.get("uptime", 0)
        if node_uptime > 0:
            lines.append(f"│ ⏱️ 节点运行: {_format_uptime(node_uptime)}")

        lines.append("└───────────────────────")
        return "\n".join(lines)

    def fmt_brief(self, inst: dict, d_label: str, d_uuid: str) -> str:
        if not isinstance(inst, dict):
            return f"  {'[' + d_label + '] ' if d_label else ''}❓ 数据异常"

        cfg = inst.get("config", {})
        if not isinstance(cfg, dict):
            cfg = {}
        info = inst.get("info", {})
        if not isinstance(info, dict):
            info = {}

        daemon_stat = self.api.get_daemon_stats(d_uuid)

        name = cfg.get("nickname", inst.get("instanceUuid", "?")[:8])
        status = inst.get("status", -1)
        extra = ""

        if status == 3:
            current = info.get("currentPlayers", 0)
            extra = f"  👥{current}"

            cpu = daemon_stat.get("cpu", 0)
            if cpu > 0:
                extra += f"  💻{cpu:.0f}%"

            mem_used = daemon_stat.get("mem_used", 0)
            if mem_used > 0:
                extra += f"  🧠{mem_used / 1024 / 1024:.0f}MB"

        prefix = f"[{d_label}] " if d_label else ""
        return f"  {prefix}{name} — {STATUS_MAP.get(status, '❓')}{extra}"

    # ==========================================
    #  命令注册
    # ==========================================

    @filter.command("mcsm help", alias=["mcsm 帮助", "mcsm h", "mcs help", "mcs 帮助", "mcs h"])
    async def mcsm_help(self, event: AstrMessageEvent):
        err = self._pre_check(event, "help")
        if err is not None:
            if err:
                yield event.plain_result(err)
            return
        yield event.plain_result(HELP_TEXT)

    @filter.command("mcsm status", alias=["mcsm 状态", "mcsm s", "mcs status", "mcs 状态", "mcs s"])
    async def mcsm_status(self, event: AstrMessageEvent, query: str = ""):
        err = self._pre_check(event, "status")
        if err is not None:
            if err:
                yield event.plain_result(err)
            return

        query = query.strip()
        matches = await self.api.find_instances(query)
        if not matches:
            suffix = f"「{query}」" if query else ""
            yield event.plain_result(f"❌ 未找到实例{suffix}")
            return

        if query and matches:
            d_uuid, i_uuid, inst, d_label = matches[0]
            yield event.plain_result(self.fmt_detail(inst, d_label, d_uuid))
        else:
            lines = ["📋 服务器状态概览", "─────────────────────"]
            for d_uuid, i_uuid, inst, d_label in matches:
                lines.append(self.fmt_brief(inst, d_label, d_uuid))
            lines += ["─────────────────────", "💡 使用 /mcsm status <名称> 查看详情"]
            yield event.plain_result("\n".join(lines))

    @filter.command("mcsm list", alias=["mcsm 列表", "mcsm ls", "mcsm l", "mcs list", "mcs 列表", "mcs ls", "mcs l"])
    async def mcsm_list(self, event: AstrMessageEvent):
        err = self._pre_check(event, "list")
        if err is not None:
            if err:
                yield event.plain_result(err)
            return

        matches = await self.api.find_instances()
        if not matches:
            yield event.plain_result("❌ 未找到任何实例，请检查 MCSM 连接配置")
            return
        lines = ["📋 实例列表", "─────────────────────"]
        for i, (d_uuid, i_uuid, inst, _) in enumerate(matches, 1):
            cfg = inst.get("config", {})
            name = cfg.get("nickname", i_uuid[:8])
            status = STATUS_MAP.get(inst.get("status", -1), "❓")
            info = inst.get("info", {})
            version = info.get("version", "")
            ver_str = f" ({version})" if version else ""
            lines.append(f"  {i}. {name}{ver_str}  [{i_uuid[:8]}…]  {status}")
        lines += ["─────────────────────", f"共 {len(matches)} 个实例"]
        yield event.plain_result("\n".join(lines))

    @filter.command("mcsm start", alias=["mcsm 启动", "mcs start", "mcs 启动"])
    async def mcsm_start(self, event: AstrMessageEvent, query: str = ""):
        err = self._pre_check(event, "start")
        if err is not None:
            if err:
                yield event.plain_result(err)
            return
        async for r in self._do_action(event, query, "open", "启动"):
            yield r

    @filter.command("mcsm stop", alias=["mcsm 停止", "mcs stop", "mcs 停止"])
    async def mcsm_stop(self, event: AstrMessageEvent, query: str = ""):
        err = self._pre_check(event, "stop")
        if err is not None:
            if err:
                yield event.plain_result(err)
            return
        async for r in self._do_action(event, query, "stop", "停止"):
            yield r

    @filter.command("mcsm restart", alias=["mcsm 重启", "mcs restart", "mcs 重启"])
    async def mcsm_restart(self, event: AstrMessageEvent, query: str = ""):
        err = self._pre_check(event, "restart")
        if err is not None:
            if err:
                yield event.plain_result(err)
            return
        async for r in self._do_action(event, query, "restart", "重启"):
            yield r

    @filter.command("mcsm kill", alias=["mcsm 终止", "mcs kill", "mcs 终止"])
    async def mcsm_kill(self, event: AstrMessageEvent, query: str = ""):
        err = self._pre_check(event, "kill")
        if err is not None:
            if err:
                yield event.plain_result(err)
            return
        async for r in self._do_action(event, query, "kill", "强制终止"):
            yield r

    @filter.command("mcsm cmd", alias=["mcsm command", "mcsm 命令", "mcsm c", "mcs cmd", "mcs command", "mcs 命令", "mcs c"])
    async def mcsm_cmd(self, event: AstrMessageEvent, cmd_text: str = ""):
        err = self._pre_check(event, "cmd")
        if err is not None:
            if err:
                yield event.plain_result(err)
            return

        cmd_text = cmd_text.strip()
        if not cmd_text:
            yield event.plain_result(
                "❌ 用法: /mcsm cmd [实例名] <命令>\n"
                "示例: /mcsm cmd say Hello\n"
                "多实例: /mcsm cmd 生存服 say Hello"
            )
            return

        matches = await self.api.find_instances()
        running = [(d, i, inst, dl) for d, i, inst, dl in matches if inst.get("status") == 3]
        if not running:
            yield event.plain_result("❌ 没有正在运行的实例，请先启动")
            return

        target = None
        command = cmd_text

        if len(running) == 1:
            d, i, inst, _ = running[0]
            target = (d, i, inst)
        else:
            first_word = cmd_text.split(None, 1)[0]
            matched = False
            for d, i, inst, dl in running:
                name = inst.get("config", {}).get("nickname", "")
                if name and first_word.lower() == name.lower():
                    target = (d, i, inst)
                    remaining = cmd_text[len(first_word):].strip()
                    if remaining:
                        command = remaining
                    matched = True
                    break
            if not matched:
                for d, i, inst, dl in running:
                    name = inst.get("config", {}).get("nickname", "")
                    if name and first_word.lower() in name.lower():
                        target = (d, i, inst)
                        remaining = cmd_text[len(first_word):].strip()
                        if remaining:
                            command = remaining
                        matched = True
                        break
            if not matched:
                names = [m[2].get("config", {}).get("nickname", m[1][:8]) for m in running]
                yield event.plain_result(
                    "⚠️ 多个实例运行中，请指定实例名:\n"
                    + "\n".join(f"  /mcsm cmd {n} <命令>" for n in names)
                )
                return

        if not command:
            yield event.plain_result("❌ 请输入要发送的命令")
            return

        d_uuid, i_uuid, inst = target
        name = inst.get("config", {}).get("nickname", i_uuid[:8])
        await self.api.send_command(d_uuid, i_uuid, command)
        yield event.plain_result(f"✅ → {name}: {command}")

    @filter.command("mcsm say", alias=["mcsm 喊话", "mcs say", "mcs 喊话"])
    async def mcsm_say(self, event: AstrMessageEvent, say_text: str = ""):
        err = self._pre_check(event, "cmd")
        if err is not None:
            if err:
                yield event.plain_result(err)
            return

        say_text = say_text.strip()
        if not say_text:
            yield event.plain_result(
                "❌ 用法: /mcsm say <内容>\n"
                "示例: /mcsm say 服务器将在5分钟后重启"
            )
            return

        matches = await self.api.find_instances()
        running = [(d, i, inst, dl) for d, i, inst, dl in matches if inst.get("status") == 3]
        if not running:
            yield event.plain_result("❌ 没有正在运行的实例，请先启动")
            return

        sent_names = []
        for d_uuid, i_uuid, inst, _ in running:
            name = inst.get("config", {}).get("nickname", i_uuid[:8])
            await self.api.send_command(d_uuid, i_uuid, f"say {say_text}")
            sent_names.append(name)

        if len(sent_names) == 1:
            yield event.plain_result(f"✅ → {sent_names[0]}: say {say_text}")
        else:
            yield event.plain_result(f"✅ 已广播至 {len(sent_names)} 个实例: say {say_text}")

    @filter.command("mcsm panel", alias=["mcsm 面板", "mcsm p", "mcs panel", "mcs 面板", "mcs p"])
    async def mcsm_panel(self, event: AstrMessageEvent, query: str = ""):
        err = self._pre_check(event, "panel")
        if err is not None:
            if err:
                yield event.plain_result(err)
            return

        if not HAS_PIL:
            yield event.plain_result("❌ 此功能需要 Pillow，请运行: pip install Pillow")
            return

        query = query.strip()

        matches = await self.api.find_instances()
        if not matches:
            yield event.plain_result("❌ 未找到任何实例")
            return

        if query.isdigit():
            idx = int(query)
            if idx < 1 or idx > len(matches):
                yield event.plain_result(
                    f"❌ 序号 {idx} 超出范围，当前共 {len(matches)} 个实例（1~{len(matches)}）"
                )
                return
            matches = [matches[idx - 1]]

        instances = []
        for d_uuid, i_uuid, inst, d_label in matches:
            cfg = inst.get("config", {})
            if not isinstance(cfg, dict):
                cfg = {}
            info = inst.get("info", {})
            if not isinstance(info, dict):
                info = {}

            daemon_stat = self.api.get_daemon_stats(d_uuid)

            current_players = info.get("currentPlayers", 0)
            if not isinstance(current_players, int):
                current_players = 0

            cpu = daemon_stat.get("cpu", 0)
            mem_used = daemon_stat.get("mem_used", 0)
            mem_total = daemon_stat.get("mem_total", 0)
            node_uptime = daemon_stat.get("uptime", 0)

            instances.append({
                "name":         cfg.get("nickname", i_uuid[:8]),
                "status":       inst.get("status", -1),
                "player_count": current_players,
                "max_players":  info.get("maxPlayers", "?"),
                "player_names": [],
                "cpu":          cpu,
                "memory":       mem_used,
                "max_memory":   mem_total,
                "uptime":       int(node_uptime) if node_uptime else 0,
                "port":         str(cfg.get("basePort") or cfg.get("port", "")),
                "daemon":       daemon_stat.get("hostname", "") or d_label,
            })

        bg_image = await self._get_background()

        try:
            img = render_dashboard(instances, background=bg_image)
        except Exception as e:
            logger.error(f"MCSM 面板渲染失败: {e}", exc_info=True)
            yield event.plain_result(f"❌ 渲染失败: {e}")
            return

        tmp_path = os.path.join(tempfile.gettempdir(), "mcsm_panel.png")
        try:
            img.save(tmp_path, format="PNG")
        except Exception as e:
            yield event.plain_result(f"❌ 图片保存失败: {e}")
            return

        try:
            from astrbot.api.message_components import Image as MsgImage
            yield event.chain_result([MsgImage(file=tmp_path)])
        except (ImportError, AttributeError):
            yield event.plain_result(
                f"❌ 当前 AstrBot 版本不支持发送图片消息\n图片已保存到: {tmp_path}"
            )
        except Exception as e:
            yield event.plain_result(f"❌ 发送图片失败: {e}")

    # ==========================================
    #  实例操作共用逻辑
    # ==========================================

    async def _do_action(self, event, query, action, action_name):
        query = query.strip()

        if query.isdigit():
            idx = int(query)
            all_instances = await self.api.find_instances()
            if not all_instances:
                yield event.plain_result("❌ 未找到任何实例，请检查 MCSM 连接配置")
                return
            if idx < 1 or idx > len(all_instances):
                yield event.plain_result(
                    f"❌ 序号 {idx} 超出范围，当前共 {len(all_instances)} 个实例（1~{len(all_instances)}）"
                )
                return
            d_uuid, i_uuid, inst, _ = all_instances[idx - 1]
            name = inst.get("config", {}).get("nickname", i_uuid[:8])
            status = inst.get("status", -1)
            if action == "open" and status == 3:
                yield event.plain_result(f"ℹ️ {name} 已在运行中")
                return
            if action == "stop" and status == 0:
                yield event.plain_result(f"ℹ️ {name} 已经停止")
                return
            await self.api.operate_instance(d_uuid, i_uuid, action)
            yield event.plain_result(f"✅ 已发送{action_name}指令: {name}")
            return

        matches = await self.api.find_instances(query)
        if not matches:
            yield event.plain_result(f"❌ 未找到实例: {query or '(未指定)'}")
            return
        if len(matches) > 1 and not query:
            names = [m[2].get("config", {}).get("nickname", m[1][:8]) for m in matches]
            yield event.plain_result(
                "⚠️ 存在多个实例，请指定名称:\n"
                + "\n".join(f"  /mcsm {action_name} {n}" for n in names)
            )
            return
        d_uuid, i_uuid, inst, _ = matches[0]
        name = inst.get("config", {}).get("nickname", i_uuid[:8])
        status = inst.get("status", -1)
        if action == "open" and status == 3:
            yield event.plain_result(f"ℹ️ {name} 已在运行中")
            return
        if action == "stop" and status == 0:
            yield event.plain_result(f"ℹ️ {name} 已经停止")
            return
        await self.api.operate_instance(d_uuid, i_uuid, action)
        yield event.plain_result(f"✅ 已发送{action_name}指令: {name}")

    # ==========================================
    #  生命周期
    # ==========================================

    async def terminate(self):
        await self.api.close()
        self._bg_current_img = None
        self._bg_current_key = None
        logger.info("astrbot-plugin-mcsm-status 已卸载")
