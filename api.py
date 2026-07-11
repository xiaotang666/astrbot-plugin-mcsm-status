"""
MCSManager Web API 客户端
基于实测 MCSM v10 数据结构
CPU/内存 通过 overview API 获取节点系统级数据
"""

import aiohttp
from typing import Optional, List, Tuple, Dict
from astrbot.api import logger


class McsmApiClient:
    """MCSManager API 客户端"""

    def __init__(self, base_url: str, api_key: str, timeout: int = 10):
        self.base_url: str = base_url.rstrip("/")
        self.api_key: str = api_key
        self.timeout: int = timeout
        self._session: Optional[aiohttp.ClientSession] = None
        # 缓存节点系统统计数据（来自 overview API）
        self._daemon_stats: Dict[str, dict] = {}

    # ═══════════════════════════════════════════
    #  HTTP 客户端
    # ═══════════════════════════════════════════

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )
        return self._session

    async def _api(self, method: str, path: str, params: dict = None, json_data: dict = None) -> dict:
        session = await self._ensure_session()
        url = f"{self.base_url}{path}"
        query_params = {"apikey": self.api_key}
        if params:
            query_params.update(params)
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "X-Requested-With": "XMLHttpRequest",
        }
        try:
            async with session.request(
                method=method.upper(), url=url, params=query_params,
                json=json_data, headers=headers,
            ) as resp:
                if resp.status != 200:
                    try:
                        err_json = await resp.json()
                        err_msg = err_json.get("error") or err_json.get("message") or str(err_json)
                    except Exception:
                        err_msg = await resp.text()
                    raise RuntimeError(f"API 错误 [{resp.status}]: {err_msg[:200]}")
                return await resp.json()
        except aiohttp.ClientError as e:
            raise aiohttp.ClientError(f"连接 MCSManager 失败: {e}") from e

    # ═══════════════════════════════════════════
    #  节点系统统计（来自 /api/overview）
    # ═══════════════════════════════════════════

    def _update_daemon_stats(self, nodes: list):
        """
        从 overview API 的 remote 数组中提取每个节点的系统级 CPU/内存数据。

        overview 返回结构:
        remote[].system.cpuUsage  = float (0~1, 需要 *100 转百分比)
        remote[].system.totalmem  = int (字节, 系统总内存)
        remote[].system.freemem   = int (字节, 系统空闲内存)
        remote[].system.memUsage  = float (0~1, 内存使用率)
        remote[].system.hostname  = str
        remote[].system.uptime    = float (秒, 系统运行时长)
        """
        for node in nodes:
            if not isinstance(node, dict):
                continue
            uuid = node.get("uuid", "")
            if not uuid:
                continue

            system = node.get("system", {})
            if not isinstance(system, dict):
                continue

            total = system.get("totalmem", 0) or 0
            free = system.get("freemem", 0) or 0
            cpu_usage = system.get("cpuUsage", 0) or 0
            mem_usage = system.get("memUsage", 0) or 0

            self._daemon_stats[uuid] = {
                "cpu": round(cpu_usage * 100, 1),
                "mem_used": max(0, total - free),
                "mem_total": total,
                "mem_percent": round(mem_usage * 100, 1),
                "hostname": system.get("hostname", ""),
                "uptime": system.get("uptime", 0) or 0,
                "os_type": system.get("type", ""),
                "os_version": system.get("version", ""),
            }

    def get_daemon_stats(self, daemon_uuid: str) -> dict:
        """获取指定节点的系统统计数据"""
        return self._daemon_stats.get(daemon_uuid, {
            "cpu": 0, "mem_used": 0, "mem_total": 0, "mem_percent": 0,
        })

    def get_all_daemon_stats(self) -> Dict[str, dict]:
        """获取所有节点的系统统计数据"""
        return self._daemon_stats

    # ═══════════════════════════════════════════
    #  实例数据归一化（基于实测数据结构）
    # ═══════════════════════════════════════════

    @staticmethod
    def _normalize_instance(raw: dict) -> dict:
        """
        归一化实例数据。

        实测列表接口返回结构:
        {
          "instanceUuid": str,
          "status": int,              # 0=停止 1=停止中 2=启动中 3=运行
          "started": int,             # 不是时间戳! 可能是计数器或标志位
          "config": {
            "nickname": str,
            "type": str,              # "minecraft/java"
            "basePort": int,
            ...
          },
          "info": {
            "currentPlayers": int,    # ★ 当前在线人数(整数)
            "maxPlayers": int,        # ★ 最大人数(整数)
            "version": str,           # 服务端版本
            "mcPingOnline": bool,
            "latency": int,           # ping延迟(ms)
            "playersChart": list,
            ...
          }
        }
        """
        if not isinstance(raw, dict):
            return {}

        config = raw.get("config", {})
        if not isinstance(config, dict):
            config = {}

        info = raw.get("info", {})
        if not isinstance(info, dict):
            info = {}

        status = raw.get("status", -1)

        # ★ 玩家: currentPlayers 是 int（人数），不是列表
        current_players = info.get("currentPlayers", 0)
        if not isinstance(current_players, int):
            current_players = 0

        max_players = info.get("maxPlayers", 20)
        if not isinstance(max_players, int):
            max_players = 20

        # ★ started 不是时间戳，不用于计算运行时长
        # 仅记录原始值用于调试
        started_raw = raw.get("started")

        return {
            "instanceUuid": raw.get("instanceUuid") or raw.get("uuid") or "",
            "status": status,
            "started_raw": started_raw,
            "config": config,
            "info": {
                "currentPlayers": current_players,
                "maxPlayers": max_players,
                "version": info.get("version", ""),
                "latency": info.get("latency", 0) or 0,
                "mcPingOnline": info.get("mcPingOnline", False),
            },
        }

    # ═══════════════════════════════════════════
    #  MCSManager v10 API 封装
    # ═══════════════════════════════════════════

    async def get_overview(self) -> dict:
        """获取面板概览（包含所有节点系统信息）"""
        return await self._api("GET", "/api/overview")

    async def get_remote_services(self) -> list:
        """获取所有节点列表"""
        resp = await self._api("GET", "/api/service/remote_services")
        return resp.get("data", []) if isinstance(resp, dict) else []

    async def get_remote_service_instances(self, daemon_id: str, page: int = 1, page_size: int = 200) -> list:
        """获取指定节点下的实例列表"""
        resp = await self._api(
            "GET", "/api/service/remote_service_instances",
            params={"daemonId": daemon_id, "page": page, "page_size": page_size},
        )
        data = resp.get("data", {}) if isinstance(resp, dict) else {}
        return data.get("data", []) if isinstance(data, dict) else data

    async def operate_instance(self, daemon_id: str, instance_uuid: str, action: str) -> dict:
        """执行实例操作: open, stop, restart, kill"""
        if action not in ("open", "stop", "restart", "kill"):
            raise ValueError(f"不支持的操作: {action}")
        params = {"uuid": instance_uuid, "daemonId": daemon_id}
        paths = [
            f"/api/protected_instance/{action}",
            f"/api/service/remote_service/{daemon_id}/instance/{instance_uuid}/{action}",
        ]
        for path in paths:
            try:
                resp = await self._api("GET", path, params=params)
                return resp if isinstance(resp, dict) else {}
            except Exception:
                continue
        raise RuntimeError(f"操作 {action} 失败")

    async def send_command(self, daemon_id: str, instance_uuid: str, command: str) -> dict:
        """发送控制台命令"""
        params = {"uuid": instance_uuid, "daemonId": daemon_id, "command": command}
        paths = [
            "/api/protected_instance/command",
            f"/api/service/remote_service/{daemon_id}/instance/{instance_uuid}/command",
        ]
        for path in paths:
            try:
                resp = await self._api("GET", path, params=params)
                return resp if isinstance(resp, dict) else {}
            except Exception:
                continue
        raise RuntimeError("发送命令失败")

    # ═══════════════════════════════════════════
    #  高级封装
    # ═══════════════════════════════════════════

    async def get_services(self) -> list:
        return await self.get_remote_services()

    async def get_instances(self, daemon_uuid: str) -> list:
        return await self.get_remote_service_instances(daemon_uuid, page_size=200)

    async def get_instance_detail(self, daemon_uuid: str, instance_uuid: str) -> dict:
        """获取实例详情（该环境详情接口不可用，返回空）"""
        return {"instance": {}}

    async def find_instances(self, query: str = "") -> List[Tuple[str, str, dict, str]]:
        """
        遍历所有节点，根据名称或 UUID 模糊匹配实例。
        同时从 overview API 提取并缓存节点系统统计数据。
        """
        results: List[Tuple[str, str, dict, str]] = []
        exact: List[Tuple[str, str, dict, str]] = []

        try:
            overview = await self.get_overview()
            overview_data = overview.get("data", {})
            nodes = overview_data.get("remote", [])

            # ★ 从 overview 中提取节点系统统计（CPU/内存）
            self._update_daemon_stats(nodes)

            if not nodes:
                logger.warning("MCSM: overview 中无节点，尝试 remote_services")
                nodes = await self.get_remote_services()
        except Exception as e:
            logger.error(f"MCSM: 获取节点列表失败: {e}")
            return results

        for node in nodes:
            if not isinstance(node, dict):
                continue
            daemon_id = node.get("uuid", node.get("daemonUuid", ""))
            daemon_label = node.get("remarks") or node.get("ip") or "unknown"

            try:
                instances = await self.get_remote_service_instances(daemon_id, page_size=200)
            except Exception as e:
                logger.warning(f"MCSM: 获取节点 {daemon_label} 实例失败: {e}")
                continue

            for inst in instances:
                if not isinstance(inst, dict):
                    continue
                inst = self._normalize_instance(inst)
                nickname = inst.get("config", {}).get("nickname", "")
                inst_uuid = inst.get("instanceUuid", "")

                if not query:
                    results.append((daemon_id, inst_uuid, inst, daemon_label))
                elif query.lower() in nickname.lower() or query.lower() in inst_uuid.lower():
                    results.append((daemon_id, inst_uuid, inst, daemon_label))
                    if query.lower() == nickname.lower() or query.lower() == inst_uuid.lower():
                        exact.append((daemon_id, inst_uuid, inst, daemon_label))

        return exact if exact else results

    # ═══════════════════════════════════════════
    #  生命周期
    # ═══════════════════════════════════════════

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None