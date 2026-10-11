import json
import os
from typing import Dict, Any, List, Optional

DEFAULT_CONFIG_PATH = "config.json"
DEFAULT_TOKENS_PATH = "tokens.txt"

DEFAULT_CONFIG: Dict[str, Any] = {
    "settings": {
        "auto_rejoin_on_disconnect": True,
        "auto_connect_on_startup": True,
        "reconnect_delay_seconds": 5,
        "log_level": "INFO"
    },
    "controller_bot": {
        "enabled": False,
        "bot_token": "",
        "prefix": "!"
    },
    "accounts": [
        {
            "name": "Account 01",
            "token": "YOUR_DISCORD_TOKEN_HERE_1",
            "guild_id": "",
            "channel_id": "",
            "self_mute": False,
            "self_deaf": False,
            "self_video": False,
            "status": "online",
            "activity": {
                "type": "streaming",
                "name": "Valorant",
                "url": "https://www.twitch.tv/valorant",
                "details": "Competitive 5v5",
                "state": "Ranked Match"
            }
        },
        {
            "name": "Account 02",
            "token": "YOUR_DISCORD_TOKEN_HERE_2",
            "guild_id": "",
            "channel_id": "",
            "self_mute": True,
            "self_deaf": True,
            "self_video": False,
            "status": "online",
            "activity": {
                "type": "listening",
                "name": "Spotify",
                "details": "Starboy",
                "state": "The Weeknd"
            }
        },
        {
            "name": "Account 03",
            "token": "YOUR_DISCORD_TOKEN_HERE_3",
            "guild_id": "",
            "channel_id": "",
            "self_mute": False,
            "self_deaf": False,
            "self_video": False,
            "status": "dnd",
            "activity": {
                "type": "playing",
                "name": "Minecraft",
                "details": "Survival Mode",
                "state": "Building Base"
            }
        },
        {
            "name": "Account 04",
            "token": "YOUR_DISCORD_TOKEN_HERE_4",
            "guild_id": "",
            "channel_id": "",
            "self_mute": False,
            "self_deaf": False,
            "self_video": False,
            "status": "idle",
            "activity": {
                "type": "custom",
                "state": "In a private VC",
                "emoji": "🎧"
            }
        },
        {
            "name": "Account 05",
            "token": "YOUR_DISCORD_TOKEN_HERE_5",
            "guild_id": "",
            "channel_id": "",
            "self_mute": False,
            "self_deaf": False,
            "self_video": False,
            "status": "online",
            "activity": {
                "type": "none"
            }
        }
    ]
}

class ConfigManager:
    def __init__(self, filepath: str = DEFAULT_CONFIG_PATH):
        self.filepath = filepath
        self.data: Dict[str, Any] = {}
        self.load()

    def load(self) -> Dict[str, Any]:
        if not os.path.exists(self.filepath):
            self.data = DEFAULT_CONFIG.copy()
            self.save()
            return self.data

        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                self.data = json.load(f)
        except Exception as e:
            print(f"[Config] Error loading {self.filepath}: {e}, using defaults.")
            self.data = DEFAULT_CONFIG.copy()

        return self.data

    def save(self) -> bool:
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[Config] Failed to save {self.filepath}: {e}")
            return False

    def get_accounts(self) -> List[Dict[str, Any]]:
        return self.data.get("accounts", [])

    def get_account_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        cleaned = name.strip().lower()
        for account in self.get_accounts():
            if account.get("name", "").strip().lower() == cleaned:
                return account
        return None

    def get_account_by_identifier(self, identifier: str) -> Optional[Dict[str, Any]]:
        identifier = identifier.strip()

        exact_match = self.get_account_by_name(identifier)
        if exact_match:
            return exact_match

        prefixed_match = self.get_account_by_name(f"Account {identifier}")
        if prefixed_match:
            return prefixed_match

        if identifier.isdigit():
            padded = f"{int(identifier):02d}"
            padded_match = self.get_account_by_name(f"Account {padded}")
            if padded_match:
                return padded_match

            index = int(identifier) - 1
            accounts = self.get_accounts()
            if 0 <= index < len(accounts):
                return accounts[index]

        return None

    def add_account(self, token: str, name: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        accounts = self.get_accounts()
        if not name:
            name = f"Account {len(accounts) + 1:02d}"

        new_account = {
            "name": name,
            "token": token,
            "guild_id": kwargs.get("guild_id", ""),
            "channel_id": kwargs.get("channel_id", ""),
            "self_mute": kwargs.get("self_mute", False),
            "self_deaf": kwargs.get("self_deaf", False),
            "self_video": kwargs.get("self_video", False),
            "status": kwargs.get("status", "online"),
            "activity": kwargs.get("activity", {"type": "none"})
        }

        accounts.append(new_account)
        self.data["accounts"] = accounts
        self.save()
        return new_account

    def remove_account(self, identifier: str) -> bool:
        target = self.get_account_by_identifier(identifier)
        if not target:
            return False

        self.data["accounts"] = [
            acc for acc in self.get_accounts()
            if acc.get("name") != target.get("name")
        ]
        self.save()
        return True

    def import_tokens_from_file(self, tokens_filepath: str = DEFAULT_TOKENS_PATH) -> int:
        if not os.path.exists(tokens_filepath):
            with open(tokens_filepath, "w", encoding="utf-8") as f:
                f.write("")
            return 0

        existing_tokens = {acc.get("token") for acc in self.get_accounts()}
        imported_count = 0

        with open(tokens_filepath, "r", encoding="utf-8") as f:
            for line in f:
                raw_line = line.strip()
                if not raw_line:
                    continue

                parts = raw_line.split(":")
                token = parts[0].strip()
                channel_id = parts[1].strip() if len(parts) > 1 else ""
                guild_id = parts[2].strip() if len(parts) > 2 else ""

                if token and token not in existing_tokens:
                    self.add_account(token=token, channel_id=channel_id, guild_id=guild_id)
                    existing_tokens.add(token)
                    imported_count += 1

        if imported_count > 0:
            self.save()

        return imported_count
