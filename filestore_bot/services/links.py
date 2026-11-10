"""Create and parse file-store deep links."""

from pyrogram import Client

from ..config import Settings
from ..encoding import decode, encode

MAX_BATCH = 500


class LinkService:
    def __init__(self, settings: Settings) -> None:
        self._channel_key = abs(settings.db_channel)

    async def make_link(self, client: Client, first: int, last: int | None = None) -> str:
        raw = f"get-{first * self._channel_key}"
        if last is not None and last != first:
            raw += f"-{last * self._channel_key}"
        me = await client.get_me()
        return f"https://t.me/{me.username}?start={encode(raw)}"

    def parse(self, token: str) -> tuple[int, int]:
        parts = decode(token).split("-")
        if parts[0] != "get":
            raise ValueError("Unsupported link type")
        first = int(parts[1]) // self._channel_key
        last = int(parts[2]) // self._channel_key if len(parts) > 2 else first
        if not 0 < first <= last or last - first >= MAX_BATCH:
            raise ValueError("Invalid file range")
        return first, last
