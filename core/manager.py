import asyncio
import logging
import random
from typing import Dict, List, Optional, Any
from .client import DiscordAccountClient
from .config import ConfigManager

logger = logging.getLogger("VCJoiner.Manager")

class VoiceJoinerManager:
    def __init__(self, config_manager: Optional[ConfigManager] = None):
        self.config_manager = config_manager or ConfigManager()
        self.clients: Dict[str, DiscordAccountClient] = {}
        self.client_tasks: Dict[str, asyncio.Task] = {}
        self.is_running = False

    def get_client(self, identifier: str) -> Optional[DiscordAccountClient]:
        cleaned = str(identifier).strip()

        for name, client in self.clients.items():
            if name.lower() == cleaned.lower():
                return client

        target_name = f"Account {cleaned}".lower()
        for name, client in self.clients.items():
            if name.lower() == target_name:
                return client

        if cleaned.isdigit():
            padded_name = f"Account {int(cleaned):02d}".lower()
            for name, client in self.clients.items():
                if name.lower() == padded_name:
                    return client

            idx = int(cleaned) - 1
            client_list = list(self.clients.values())
            if 0 <= idx < len(client_list):
                return client_list[idx]

        return None

    def get_all_clients(self) -> List[DiscordAccountClient]:
        return list(self.clients.values())

    def resolve_targets(self, selector: str) -> List[DiscordAccountClient]:
        cleaned = selector.strip().lower()
        if cleaned in ("all", "*"):
            return self.get_all_clients()
        client = self.get_client(selector)
        return [client] if client else []

    def init_clients_from_config(self):
        accounts = self.config_manager.get_accounts()
        for acc in accounts:
            token = acc.get("token", "").strip()
            if not token or token.startswith("YOUR_DISCORD_TOKEN"):
                continue

            name = acc.get("name", f"Account {len(self.clients) + 1:02d}")
            if name in self.clients:
                continue

            client = DiscordAccountClient(
                name=name,
                token=token,
                channel_id=acc.get("channel_id"),
                guild_id=acc.get("guild_id"),
                self_mute=acc.get("self_mute", False),
                self_deaf=acc.get("self_deaf", False),
                self_video=acc.get("self_video", False),
                status=acc.get("status", "online"),
                activity=acc.get("activity", {"type": "none"})
            )
            self.clients[name] = client

    async def start(self):
        self.is_running = True
        self.init_clients_from_config()

        for idx, (name, client) in enumerate(self.clients.items()):
            if name not in self.client_tasks or self.client_tasks[name].done():
                if idx > 0:
                    stagger_time = random.uniform(2.0, 4.0)
                    await asyncio.sleep(stagger_time)
                self.client_tasks[name] = asyncio.create_task(client.start())

    async def stop(self):
        self.is_running = False
        for name, client in self.clients.items():
            await client.stop()

        for task in self.client_tasks.values():
            if not task.done():
                task.cancel()

        self.client_tasks.clear()

    async def join_vc(self, selector: str, channel_id: str, guild_id: Optional[str] = None) -> List[str]:
        targets = self.resolve_targets(selector)
        successes = []
        for idx, client in enumerate(targets):
            if idx > 0:
                await asyncio.sleep(random.uniform(1.2, 2.5))
            ok = await client.join_vc(channel_id, guild_id)
            if ok:
                successes.append(client.name)
                acc_conf = self.config_manager.get_account_by_name(client.name)
                if acc_conf:
                    acc_conf["channel_id"] = str(channel_id)
                    if client.guild_id:
                        acc_conf["guild_id"] = str(client.guild_id)

        if successes:
            self.config_manager.save()
        return successes

    async def leave_vc(self, selector: str) -> List[str]:
        targets = self.resolve_targets(selector)
        successes = []
        for client in targets:
            ok = await client.leave_vc()
            if ok:
                successes.append(client.name)
                acc_conf = self.config_manager.get_account_by_name(client.name)
                if acc_conf:
                    acc_conf["channel_id"] = ""

        if successes:
            self.config_manager.save()
        return successes

    async def set_activity(
        self,
        selector: str,
        activity_type: str,
        name: str,
        details: Optional[str] = None,
        state: Optional[str] = None,
        url: Optional[str] = None,
        emoji: Optional[str] = None
    ) -> List[str]:
        targets = self.resolve_targets(selector)
        activity_dict: Dict[str, Any] = {
            "type": activity_type,
            "name": name
        }
        if details:
            activity_dict["details"] = details
        if state:
            activity_dict["state"] = state
        if url:
            activity_dict["url"] = url
        if emoji:
            activity_dict["emoji"] = emoji

        successes = []
        for client in targets:
            ok = await client.update_presence(activity=activity_dict)
            if ok:
                successes.append(client.name)
                acc_conf = self.config_manager.get_account_by_name(client.name)
                if acc_conf:
                    acc_conf["activity"] = activity_dict

        if successes:
            self.config_manager.save()
        return successes

    async def set_status(self, selector: str, status: str) -> List[str]:
        targets = self.resolve_targets(selector)
        successes = []
        for client in targets:
            ok = await client.update_presence(status=status)
            if ok:
                successes.append(client.name)
                acc_conf = self.config_manager.get_account_by_name(client.name)
                if acc_conf:
                    acc_conf["status"] = status

        if successes:
            self.config_manager.save()
        return successes

    async def set_stream(
        self,
        selector: str,
        title: str,
        url: str = "https://www.twitch.tv/discord",
        details: Optional[str] = None
    ) -> List[str]:
        return await self.set_activity(
            selector=selector,
            activity_type="streaming",
            name=title,
            url=url,
            details=details or "Streaming live"
        )

    async def set_music(
        self,
        selector: str,
        song: str,
        artist: str = ""
    ) -> List[str]:
        return await self.set_activity(
            selector=selector,
            activity_type="listening",
            name="Spotify",
            details=song,
            state=artist or "Unknown Artist"
        )

    async def set_voice_state(
        self,
        selector: str,
        mute: Optional[bool] = None,
        deaf: Optional[bool] = None,
        video: Optional[bool] = None
    ) -> List[str]:
        targets = self.resolve_targets(selector)
        successes = []
        for client in targets:
            ok = await client.update_voice_state(self_mute=mute, self_deaf=deaf, self_video=video)
            if ok:
                successes.append(client.name)
                acc_conf = self.config_manager.get_account_by_name(client.name)
                if acc_conf:
                    if mute is not None:
                        acc_conf["self_mute"] = mute
                    if deaf is not None:
                        acc_conf["self_deaf"] = deaf
                    if video is not None:
                        acc_conf["self_video"] = video

        if successes:
            self.config_manager.save()
        return successes

    async def add_account(self, token: str, name: Optional[str] = None, **kwargs) -> Optional[DiscordAccountClient]:
        acc_dict = self.config_manager.add_account(token=token, name=name, **kwargs)
        acc_name = acc_dict["name"]

        client = DiscordAccountClient(
            name=acc_name,
            token=token,
            channel_id=acc_dict.get("channel_id"),
            guild_id=acc_dict.get("guild_id"),
            self_mute=acc_dict.get("self_mute", False),
            self_deaf=acc_dict.get("self_deaf", False),
            self_video=acc_dict.get("self_video", False),
            status=acc_dict.get("status", "online"),
            activity=acc_dict.get("activity", {"type": "none"})
        )
        self.clients[acc_name] = client
        if self.is_running:
            self.client_tasks[acc_name] = asyncio.create_task(client.start())
        return client

    async def remove_account(self, identifier: str) -> bool:
        client = self.get_client(identifier)
        if not client:
            return False

        name = client.name
        await client.stop()
        if name in self.client_tasks:
            self.client_tasks[name].cancel()
            del self.client_tasks[name]
        if name in self.clients:
            del self.clients[name]

        self.config_manager.remove_account(name)
        return True
