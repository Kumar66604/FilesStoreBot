"""File retrieval and delivery operations."""

import asyncio

from pyrogram import Client
from pyrogram.errors import FloodWait

from ..config import Settings


class FileService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def deliver(self, client: Client, channel_id: int, chat_id: int, first: int, last: int):
        sent = []
        ids = list(range(first, last + 1))
        for offset in range(0, len(ids), 100):
            batch = await self._get_messages(client, channel_id, ids[offset : offset + 100])
            for message in batch:
                if message.empty:
                    continue
                try:
                    sent.append(
                        await message.copy(
                            chat_id,
                            protect_content=self._settings.protect_content,
                        )
                    )
                except FloodWait as error:
                    await asyncio.sleep(error.value)
                    sent.append(
                        await message.copy(
                            chat_id,
                            protect_content=self._settings.protect_content,
                        )
                    )
                except Exception:
                    continue
        return sent

    async def store(self, message, channel_id: int):
        return await message.copy(channel_id)

    @staticmethod
    async def _get_messages(client: Client, channel_id: int, ids: list[int]):
        try:
            result = await client.get_messages(channel_id, ids)
        except FloodWait as error:
            await asyncio.sleep(error.value)
            result = await client.get_messages(channel_id, ids)
        return result if isinstance(result, list) else [result]
