"""Private user-facing handlers."""

import asyncio

from pyrogram import Client, filters

from ..config import Settings
from ..services.files import FileService
from ..services.links import LinkService


def register_user_handlers(app: Client, settings: Settings, users, links: LinkService, files: FileService) -> None:
    @app.on_message(filters.command("start") & filters.private)
    async def start_handler(client: Client, message) -> None:
        await users.update_one(
            {"_id": message.from_user.id},
            {"$set": {"name": message.from_user.first_name}},
            upsert=True,
        )
        if len(message.command) < 2:
            await message.reply(f"Hi {message.from_user.first_name}! Open a file link to get your files.")
            return
        try:
            first, last = links.parse(message.command[1])
        except (ValueError, UnicodeError, IndexError):
            await message.reply("Invalid or expired link.")
            return
        sent = await files.deliver(client, settings.db_channel, message.chat.id, first, last)
        if not sent:
            await message.reply("Files not found.")
            return
        if settings.auto_delete_seconds:
            note = await message.reply(
                f"These files will be deleted in {settings.auto_delete_seconds // 60} min. Save them now."
            )
            asyncio.create_task(_delete_later(sent + [note], settings.auto_delete_seconds))


async def _delete_later(messages, delay: int) -> None:
    await asyncio.sleep(delay)
    for message in messages:
        try:
            await message.delete()
        except Exception:
            continue
