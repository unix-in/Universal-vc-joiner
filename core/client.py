import asyncio
import base64
import json
import logging
import random
import time
from typing import Dict, Any, Optional, Callable
import aiohttp

from .presence import PresenceBuilder

logger = logging.getLogger("VCJoiner.Client")

DISCORD_API_BASE = "https://discord.com/api/v10"
DISCORD_GATEWAY_URL = "wss://gateway.discord.gg/?v=10&encoding=json"

CLIENT_PROPERTIES = {
    "os": "Windows",
    "browser": "Discord Client",
    "release_channel": "stable",
    "client_version": "1.0.9175",
    "os_version": "10.0.19045",
    "os_arch": "x64",
    "app_arch": "x64",
    "system_locale": "en-US",
    "browser_user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) discord/1.0.9175 Chrome/128.0.6613.186 Electron/32.2.7 Safari/537.36",
    "browser_version": "32.2.7",
    "client_build_number": 348521,
    "native_build_number": None,
    "client_event_source": None
}

ENCODED_SUPER_PROPERTIES = base64.b64encode(
    json.dumps(CLIENT_PROPERTIES, separators=(",", ":")).encode("utf-8")
).decode("utf-8")

FATAL_CLOSE_CODES = {4004, 4010, 4011, 4012, 4013, 4014}

class DiscordAccountClient:
    def __init__(
        self,
        name: str,
        token: str,
        channel_id: Optional[str] = None,
        guild_id: Optional[str] = None,
        self_mute: bool = False,
        self_deaf: bool = False,
        self_video: bool = False,
        status: str = "online",
        activity: Optional[Dict[str, Any]] = None,
        on_status_change: Optional[Callable[[str, str], None]] = None
    ):
        self.name = name
        self.token = token.strip()
        self.channel_id = str(channel_id).strip() if channel_id else None
        self.guild_id = str(guild_id).strip() if guild_id else None
        self.self_mute = self_mute
        self.self_deaf = self_deaf
        self.self_video = self_video
        self.status = status
        self.activity = activity or {"type": "none"}
        self.on_status_change = on_status_change

        self.user_data: Dict[str, Any] = {}
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self.session: Optional[aiohttp.ClientSession] = None
        self.heartbeat_task: Optional[asyncio.Task] = None
        self.sequence: Optional[int] = None
        self.session_id: Optional[str] = None
        self.resume_gateway_url: Optional[str] = None
        self.last_heartbeat_ack = True
        self.is_running = False
        self.state_desc = "OFFLINE"
        self.in_vc = False
        self.current_channel_name = ""
        self.ping_ms: float = 0.0
        self._last_heartbeat_time = 0.0
        self._backoff_delay = 3.0

    @property
    def username(self) -> str:
        if self.user_data:
            tag = self.user_data.get("discriminator", "0")
            user = self.user_data.get("username", "Unknown")
            if tag and tag != "0":
                return f"{user} ({tag})"
            return user
        return "Not Authenticated"

    def _set_state(self, state: str):
        self.state_desc = state
        if self.on_status_change:
            try:
                self.on_status_change(self.name, state)
            except Exception:
                pass

    def get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": self.token,
            "Content-Type": "application/json",
            "User-Agent": CLIENT_PROPERTIES["browser_user_agent"],
            "X-Super-Properties": ENCODED_SUPER_PROPERTIES,
            "X-Discord-Locale": "en-US",
            "Sec-Ch-Ua": '"Chromium";v="128", "Not;A=Brand";v="24"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"'
        }

    async def fetch_user_info(self) -> bool:
        try:
            if not self.session or self.session.closed:
                self.session = aiohttp.ClientSession()

            async with self.session.get(f"{DISCORD_API_BASE}/users/@me", headers=self.get_headers()) as resp:
                if resp.status == 200:
                    self.user_data = await resp.json()
                    self._backoff_delay = 3.0
                    return True
                elif resp.status == 429:
                    rate_data = await resp.json()
                    wait_time = float(rate_data.get("retry_after", 5.0))
                    logger.warning(f"[{self.name}] Rate limit encountered, waiting {wait_time}s")
                    await asyncio.sleep(wait_time)
                    return await self.fetch_user_info()
                elif resp.status in (401, 403):
                    logger.error(f"[{self.name}] Unauthorized (HTTP {resp.status}). Check token.")
                    return False
                else:
                    logger.error(f"[{self.name}] API request failed with status {resp.status}")
                    return False
        except Exception as e:
            logger.error(f"[{self.name}] User info exception: {e}")
            return False

    async def resolve_channel_and_guild(self, channel_id: str) -> Optional[str]:
        if self.guild_id:
            return self.guild_id

        try:
            if not self.session or self.session.closed:
                self.session = aiohttp.ClientSession()

            async with self.session.get(f"{DISCORD_API_BASE}/channels/{channel_id}", headers=self.get_headers()) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    guild_id = data.get("guild_id")
                    self.current_channel_name = data.get("name", channel_id)
                    return guild_id
                elif resp.status == 429:
                    rate_data = await resp.json()
                    wait_time = float(rate_data.get("retry_after", 5.0))
                    await asyncio.sleep(wait_time)
                    return await self.resolve_channel_and_guild(channel_id)
        except Exception as e:
            logger.debug(f"[{self.name}] Channel resolution exception: {e}")

        return None

    async def start(self):
        self.is_running = True
        self._set_state("STARTING")

        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession()

        is_valid_token = await self.fetch_user_info()
        if not is_valid_token:
            self._set_state("INVALID_TOKEN")
            logger.error(f"[{self.name}] Token is invalid or unauthorized. Stopping connection to prevent suspension.")
            return

        while self.is_running:
            try:
                self._set_state("CONNECTING")
                target_gateway = self.resume_gateway_url or DISCORD_GATEWAY_URL

                async with self.session.ws_connect(
                    target_gateway,
                    headers={"User-Agent": CLIENT_PROPERTIES["browser_user_agent"]},
                    max_msg_size=0,
                    autoclose=False
                ) as ws:
                    self.ws = ws
                    self.last_heartbeat_ack = True
                    self._backoff_delay = 3.0
                    await self._handle_connection()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[{self.name}] Gateway exception: {e}")
                self._set_state("DISCONNECTED")

            if self.is_running:
                jitter = random.uniform(1.0, 3.0)
                sleep_duration = self._backoff_delay + jitter
                self._backoff_delay = min(self._backoff_delay * 1.5, 45.0)
                await asyncio.sleep(sleep_duration)

    async def _handle_connection(self):
        async for msg in self.ws:
            if not self.is_running:
                break

            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                opcode = data.get("op")
                payload = data.get("d")
                seq = data.get("s")
                event_name = data.get("t")

                if seq is not None:
                    self.sequence = seq

                if opcode == 10:
                    heartbeat_interval = payload.get("heartbeat_interval", 41250) / 1000.0
                    if self.heartbeat_task and not self.heartbeat_task.done():
                        self.heartbeat_task.cancel()
                    self.heartbeat_task = asyncio.create_task(self._heartbeat_loop(heartbeat_interval))

                    if self.session_id and self.sequence:
                        await self._resume()
                    else:
                        await self._identify()

                elif opcode == 11:
                    self.last_heartbeat_ack = True
                    if self._last_heartbeat_time > 0:
                        self.ping_ms = round((time.time() - self._last_heartbeat_time) * 1000, 1)

                elif opcode == 1:
                    await self._send_heartbeat()

                elif opcode == 7:
                    logger.info(f"[{self.name}] Gateway requested reconnection.")
                    break

                elif opcode == 9:
                    can_resume = payload is True
                    logger.warning(f"[{self.name}] Invalid session received (can_resume={can_resume})")
                    if not can_resume:
                        self.session_id = None
                        self.sequence = None
                    await asyncio.sleep(random.uniform(1.5, 3.5))
                    await self._identify()

                elif opcode == 0:
                    await self._handle_dispatch(event_name, payload)

            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                close_code = self.ws.close_code
                logger.warning(f"[{self.name}] Gateway closed with code {close_code}")
                if close_code in FATAL_CLOSE_CODES:
                    logger.critical(f"[{self.name}] Fatal close code {close_code}. Stopping account to prevent suspension.")
                    self.is_running = False
                    self._set_state("BLOCKED")
                break

    async def _heartbeat_loop(self, interval: float):
        try:
            initial_jitter = interval * random.uniform(0.1, 0.4)
            await asyncio.sleep(initial_jitter)

            while self.is_running and self.ws and not self.ws.closed:
                if not self.last_heartbeat_ack:
                    logger.warning(f"[{self.name}] Heartbeat timeout, reconnecting safely...")
                    if self.ws:
                        await self.ws.close()
                    break

                self.last_heartbeat_ack = False
                await self._send_heartbeat()
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"[{self.name}] Heartbeat error: {e}")

    async def _send_heartbeat(self):
        if self.ws and not self.ws.closed:
            self._last_heartbeat_time = time.time()
            await self.ws.send_json({"op": 1, "d": self.sequence})

    async def _identify(self):
        presence_payload = PresenceBuilder.from_dict(self.activity, status=self.status)

        payload = {
            "op": 2,
            "d": {
                "token": self.token,
                "capabilities": 8189,
                "properties": CLIENT_PROPERTIES,
                "presence": presence_payload.get("d"),
                "compress": False,
                "client_state": {
                    "guild_versions": {},
                    "highest_last_message_id": "0",
                    "read_state_version": 0,
                    "user_guild_settings_version": -1,
                    "user_settings_version": -1
                }
            }
        }
        await self.ws.send_json(payload)

    async def _resume(self):
        payload = {
            "op": 6,
            "d": {
                "token": self.token,
                "session_id": self.session_id,
                "seq": self.sequence
            }
        }
        await self.ws.send_json(payload)

    async def _handle_dispatch(self, event_type: str, data: Dict[str, Any]):
        if event_type == "READY":
            self.session_id = data.get("session_id")
            self.resume_gateway_url = data.get("resume_gateway_url")
            user = data.get("user", {})
            self.user_data = user
            self._set_state("READY")
            logger.info(f"[{self.name}] Successfully authenticated as {self.username}")

            if self.channel_id:
                delay = random.uniform(1.2, 2.5)
                await asyncio.sleep(delay)
                await self.join_vc(self.channel_id, self.guild_id)

        elif event_type == "RESUMED":
            self._set_state("READY" if not self.in_vc else "IN_VC")
            logger.info(f"[{self.name}] Gateway session successfully resumed.")

        elif event_type == "VOICE_STATE_UPDATE":
            user_id = data.get("user_id")
            if user_id == self.user_data.get("id"):
                chan_id = data.get("channel_id")
                if chan_id:
                    self.in_vc = True
                    self.channel_id = chan_id
                    self.guild_id = data.get("guild_id", self.guild_id)
                    self._set_state("IN_VC")
                else:
                    self.in_vc = False
                    self._set_state("ONLINE")

    async def join_vc(self, channel_id: str, guild_id: Optional[str] = None) -> bool:
        self.channel_id = str(channel_id).strip()
        if guild_id:
            self.guild_id = str(guild_id).strip()
        elif not self.guild_id:
            resolved_guild = await self.resolve_channel_and_guild(self.channel_id)
            if resolved_guild:
                self.guild_id = resolved_guild

        if not self.guild_id:
            logger.warning(f"[{self.name}] Cannot join VC: Guild ID required for channel {channel_id}.")
            return False

        if not self.ws or self.ws.closed:
            logger.warning(f"[{self.name}] Gateway not connected.")
            return False

        payload = {
            "op": 4,
            "d": {
                "guild_id": self.guild_id,
                "channel_id": self.channel_id,
                "self_mute": self.self_mute,
                "self_deaf": self.self_deaf,
                "self_video": self.self_video
            }
        }
        await self.ws.send_json(payload)
        self.in_vc = True
        self._set_state("IN_VC")
        logger.info(f"[{self.name}] Joined voice channel {self.channel_id} in guild {self.guild_id}")
        return True

    async def leave_vc(self) -> bool:
        if not self.ws or self.ws.closed or not self.guild_id:
            self.in_vc = False
            self.channel_id = None
            self._set_state("ONLINE")
            return False

        payload = {
            "op": 4,
            "d": {
                "guild_id": self.guild_id,
                "channel_id": None,
                "self_mute": False,
                "self_deaf": False,
                "self_video": False
            }
        }
        await self.ws.send_json(payload)
        self.in_vc = False
        self.channel_id = None
        self._set_state("ONLINE")
        logger.info(f"[{self.name}] Left voice channel.")
        return True

    async def update_voice_state(
        self,
        self_mute: Optional[bool] = None,
        self_deaf: Optional[bool] = None,
        self_video: Optional[bool] = None
    ) -> bool:
        if self_mute is not None:
            self.self_mute = self_mute
        if self_deaf is not None:
            self.self_deaf = self_deaf
        if self_video is not None:
            self.self_video = self_video

        if self.in_vc and self.guild_id and self.channel_id and self.ws and not self.ws.closed:
            payload = {
                "op": 4,
                "d": {
                    "guild_id": self.guild_id,
                    "channel_id": self.channel_id,
                    "self_mute": self.self_mute,
                    "self_deaf": self.self_deaf,
                    "self_video": self.self_video
                }
            }
            await self.ws.send_json(payload)
            return True
        return False

    async def update_presence(
        self,
        status: Optional[str] = None,
        activity: Optional[Dict[str, Any]] = None
    ) -> bool:
        if status:
            self.status = status
        if activity:
            self.activity = activity

        if not self.ws or self.ws.closed:
            return False

        payload = PresenceBuilder.from_dict(self.activity, status=self.status)
        await self.ws.send_json(payload)
        logger.info(f"[{self.name}] Updated presence: status={self.status}, type={self.activity.get('type')}")
        return True

    async def stop(self):
        self.is_running = False
        if self.in_vc:
            try:
                await self.leave_vc()
            except Exception:
                pass

        if self.heartbeat_task and not self.heartbeat_task.done():
            self.heartbeat_task.cancel()

        if self.ws and not self.ws.closed:
            await self.ws.close()

        if self.session and not self.session.closed:
            await self.session.close()

        self._set_state("OFFLINE")
