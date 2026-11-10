"""Admin-only upload and batch-link handlers."""

from pyrogram import Client, filters

from ..config import Settings
from ..services.files import FileService
from ..services.links import LinkService
from ..state import BatchState


def forwarded_message_info(message):
    """Return the original chat and message IDs across Pyrogram versions."""
    origin = getattr(message, "forward_origin", None)
    if origin is not None and getattr(origin, "chat", None):
        return origin.chat.id, getattr(origin, "message_id", None)
    chat = getattr(message, "forward_from_chat", None)
    if chat:
        return chat.id, getattr(message, "forward_from_message_id", None)
    return None, None


def register_admin_handlers(app: Client, settings: Settings, links: LinkService, files: FileService, state: BatchState) -> None:
    admin_only = filters.user(settings.admins)

    @app.on_message(filters.command("batch") & filters.private & admin_only)
    async def batch_handler(_client: Client, message) -> None:
        state.start(message.from_user.id)
        await message.reply("Forward the FIRST message from the DB channel (or /cancel).")

    @app.on_message(filters.command("cancel") & filters.private & admin_only)
    async def cancel_handler(_client: Client, message) -> None:
        state.cancel(message.from_user.id)
        await message.reply("Cancelled.")

    @app.on_message(filters.private & admin_only & ~filters.command(["start", "batch", "cancel"]))
    async def admin_message_handler(client: Client, message) -> None:
        admin_id = message.from_user.id
        pending = state.get(admin_id)
        if pending:
            chat_id, message_id = forwarded_message_info(message)
            if chat_id != settings.db_channel or not message_id:
                await message.reply("Please forward a message from the DB channel.")
                return
            if pending["step"] == "first":
                pending.update(step="last", first=message_id)
                await message.reply("Now forward the LAST message.")
                return
            first, last = sorted((int(pending["first"]), message_id))
            state.cancel(admin_id)
            await message.reply(f"Batch link:\n{await links.make_link(client, first, last)}")
            return
        if message.media:
            stored = await files.store(message, settings.db_channel)
            await message.reply(f"Link:\n{await links.make_link(client, stored.id)}")
