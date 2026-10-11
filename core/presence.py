from typing import Dict, Any, Optional
import time

class PresenceBuilder:
    ACTIVITY_TYPES = {
        "playing": 0,
        "streaming": 1,
        "listening": 2,
        "watching": 3,
        "custom": 4,
        "competing": 5,
        "none": -1
    }

    VALID_STATUSES = ["online", "idle", "dnd", "invisible"]

    @staticmethod
    def build(
        status: str = "online",
        activity_type: str = "none",
        name: str = "",
        details: Optional[str] = None,
        state: Optional[str] = None,
        url: Optional[str] = None,
        emoji: Optional[str] = None
    ) -> Dict[str, Any]:
        normalized_status = status.lower()
        if normalized_status not in PresenceBuilder.VALID_STATUSES:
            normalized_status = "online"

        type_code = PresenceBuilder.ACTIVITY_TYPES.get(str(activity_type).lower(), -1)
        now_ms = int(time.time() * 1000)
        activities = []

        if type_code == 0:
            activity_payload = {
                "name": name or "Playing",
                "type": 0,
                "created_at": now_ms
            }
            if details:
                activity_payload["details"] = details
            if state:
                activity_payload["state"] = state
            activities.append(activity_payload)

        elif type_code == 1:
            activity_payload = {
                "name": name or "Live Stream",
                "type": 1,
                "url": url or "https://www.twitch.tv/discord",
                "created_at": now_ms
            }
            if details:
                activity_payload["details"] = details
            if state:
                activity_payload["state"] = state
            activities.append(activity_payload)

        elif type_code == 2:
            is_spotify = (name or "").lower() == "spotify"
            activity_payload = {
                "name": name or "Spotify",
                "type": 2,
                "created_at": now_ms
            }
            if details:
                activity_payload["details"] = details
            if state:
                activity_payload["state"] = state
            if is_spotify:
                activity_payload["party"] = {"id": f"spotify:{int(time.time())}"}
                activity_payload["flags"] = 48
            activities.append(activity_payload)

        elif type_code == 3:
            activity_payload = {
                "name": name or "Video",
                "type": 3,
                "created_at": now_ms
            }
            if details:
                activity_payload["details"] = details
            if state:
                activity_payload["state"] = state
            activities.append(activity_payload)

        elif type_code == 4:
            activity_payload = {
                "name": "Custom Status",
                "type": 4,
                "state": state or name or "",
                "created_at": now_ms
            }
            if emoji:
                activity_payload["emoji"] = {
                    "name": emoji,
                    "id": None,
                    "animated": False
                }
            activities.append(activity_payload)

        elif type_code == 5:
            activity_payload = {
                "name": name or "Tournament",
                "type": 5,
                "created_at": now_ms
            }
            if details:
                activity_payload["details"] = details
            if state:
                activity_payload["state"] = state
            activities.append(activity_payload)

        return {
            "op": 3,
            "d": {
                "since": now_ms if normalized_status == "idle" else None,
                "activities": activities,
                "status": normalized_status,
                "afk": normalized_status == "idle"
            }
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], status: str = "online") -> Dict[str, Any]:
        return cls.build(
            status=status,
            activity_type=data.get("type", "none"),
            name=data.get("name", ""),
            details=data.get("details"),
            state=data.get("state"),
            url=data.get("url"),
            emoji=data.get("emoji")
        )
