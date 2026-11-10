"""Admin-only upload and batch-link handlers."""

from pyrogram import Client, filters

from ..config import Settings
from ..services.files import FileService
from ..services.links import LinkService
from ..services.subscriptions import SubscriptionService
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


def register_admin_handlers(
    app: Client,
    settings: Settings,
    links: LinkService,
    files: FileService,
    state: BatchState,
    subscriptions: SubscriptionService,
) -> None:
    admin_only = filters.user(settings.admins)

    @app.on_message(filters.command("help") & filters.private & admin_only)
    async def admin_help_handler(_client: Client, message) -> None:
        await message.reply(
            "FilesStore Bot - admin manual\n\n"
            "FILE MANAGEMENT\n"
            "Send any media directly to the bot to store it and generate a link.\n"
            "/batch - Create a link for a range of stored messages\n"
            "  1. Send /batch\n"
            "  2. Forward the first DB-channel message\n"
            "  3. Forward the last DB-channel message\n"
            "/cancel - Cancel the current batch operation\n\n"
            "SUBSCRIPTION PACKS\n"
            "/addpack ID STARS DAYS UPI_AMOUNT [NAME]\n"
            "  Example: /addpack monthly 100 30 99 Monthly Plan\n"
            "/listpacks - List all available packs\n"
            "/delpack ID - Remove a pack (at least one must remain)\n\n"
            "UPI ACCOUNTS\n"
            "/addupi ID UPI_ID [LABEL]\n"
            "  Example: /addupi primary example@upi Main Account\n"
            "/listupi - List configured UPI accounts\n"
            "/delupi ID - Remove a UPI account\n\n"
            "UPI APPROVAL\n"
            "/approve USER_ID - Approve that user's pending UPI payment\n"
            "Before approving, verify the UTR, amount, selected pack, and destination account.\n\n"
            "OTHER\n"
            "/help - Show this admin manual\n"
            "Admins bypass the free-file limit and subscription checks."
        )

    @app.on_message(filters.command("addpack") & filters.private & admin_only)
    async def add_pack_handler(_client: Client, message) -> None:
        if len(message.command) < 5:
            await message.reply("Usage: /addpack ID STARS DAYS UPI_AMOUNT [NAME]")
            return
        try:
            pack_id, stars, days, upi_amount = message.command[1:5]
            pack = await subscriptions.add_pack(
                pack_id.lower(),
                " ".join(message.command[5:]) or pack_id,
                int(stars),
                int(days),
                upi_amount,
            )
        except (ValueError, TypeError) as error:
            await message.reply(f"Could not add pack: {error}")
            return
        await message.reply(f"Pack added: `{pack['id']}` - {pack['name']}, {pack['days']} days, {pack['stars']} Stars")

    @app.on_message(filters.command("listpacks") & filters.private & admin_only)
    async def list_packs_handler(_client: Client, message) -> None:
        packs = await subscriptions.list_packs()
        await message.reply("Subscription packs:\n" + "\n".join(
            f"- `{pack['id']}`: {pack['name']} | {pack['days']} days | {pack['stars']} Stars | Rs {pack['upi_amount']}"
            for pack in packs
        ))

    @app.on_message(filters.command("delpack") & filters.private & admin_only)
    async def delete_pack_handler(_client: Client, message) -> None:
        if len(message.command) < 2:
            await message.reply("Usage: /delpack ID")
            return
        try:
            deleted = await subscriptions.delete_pack(message.command[1].lower())
        except ValueError as error:
            await message.reply(str(error))
            return
        await message.reply("Pack deleted." if deleted else "Pack ID not found.")

    @app.on_message(filters.command("addupi") & filters.private & admin_only)
    async def add_upi_handler(_client: Client, message) -> None:
        if len(message.command) < 3:
            await message.reply("Usage: /addupi ID UPI_ID [LABEL]")
            return
        try:
            account = await subscriptions.add_upi_account(
                message.command[1].lower(),
                " ".join(message.command[3:]) or message.command[1],
                message.command[2],
            )
        except ValueError as error:
            await message.reply(f"Could not add UPI account: {error}")
            return
        await message.reply(f"UPI account added: `{account['id']}` - {account['label']}")

    @app.on_message(filters.command("listupi") & filters.private & admin_only)
    async def list_upi_handler(_client: Client, message) -> None:
        accounts = await subscriptions.list_upi_accounts()
        if not accounts:
            await message.reply("No UPI accounts configured.")
            return
        await message.reply("UPI accounts:\n" + "\n".join(
            f"- `{account['id']}`: {account['label']} - `{account['upi_id']}`" for account in accounts
        ))

    @app.on_message(filters.command("delupi") & filters.private & admin_only)
    async def delete_upi_handler(_client: Client, message) -> None:
        if len(message.command) < 2:
            await message.reply("Usage: /delupi ID")
            return
        deleted = await subscriptions.delete_upi_account(message.command[1].lower())
        await message.reply("UPI account deleted." if deleted else "UPI account ID not found.")

    @app.on_message(filters.command("approve") & filters.private & admin_only)
    async def approve_upi_handler(client: Client, message) -> None:
        if len(message.command) < 2:
            await message.reply("Usage: /approve USER_ID")
            return
        try:
            user_id = int(message.command[1])
        except ValueError:
            await message.reply("USER_ID must be a number.")
            return
        pending = await subscriptions.get_upi_pending(user_id)
        if not pending:
            await message.reply("No pending UPI payment was found for that user.")
            return
        pack = await subscriptions.get_pack(pending["pack_id"])
        if not pack:
            await message.reply("The pending payment's pack no longer exists.")
            return
        expiry = await subscriptions.activate(user_id, "upi", pack["days"])
        await subscriptions.clear_upi_pending(user_id)
        await client.send_message(user_id, f"UPI payment approved ✅\nYour subscription is active until {expiry:%Y-%m-%d %H:%M} UTC.")
        await message.reply(f"Subscription activated for `{user_id}` until {expiry:%Y-%m-%d %H:%M} UTC.")

    @app.on_callback_query(filters.regex(r"^upireview:(approve|decline):(-?\d+)$") & admin_only)
    async def review_upi_handler(client: Client, query) -> None:
        action, raw_user_id = query.matches[0].groups()
        user_id = int(raw_user_id)
        await query.answer()
        pending = await subscriptions.get_upi_pending(user_id)
        if not pending:
            await query.message.edit_text(f"UPI review already completed for `{user_id}`.")
            return
        if action == "decline":
            await subscriptions.clear_upi_pending(user_id)
            await client.send_message(
                user_id,
                "Your UPI payment proof was declined. Please check the payment details and submit a new proof if needed.",
            )
            await query.message.edit_text(f"UPI payment declined for `{user_id}`.")
            return
        pack = await subscriptions.get_pack(pending["pack_id"])
        if not pack:
            await query.message.edit_text(f"UPI review failed for `{user_id}`: the selected pack no longer exists.")
            return
        expiry = await subscriptions.activate(user_id, "upi", pack["days"])
        await subscriptions.clear_upi_pending(user_id)
        await client.send_message(
            user_id,
            f"UPI payment approved. Your subscription is active until {expiry:%Y-%m-%d %H:%M} UTC.",
        )
        await query.message.edit_text(
            f"UPI payment approved for `{user_id}`. Subscription active until {expiry:%Y-%m-%d %H:%M} UTC."
        )

    @app.on_message(filters.command("batch") & filters.private & admin_only)
    async def batch_handler(_client: Client, message) -> None:
        state.start(message.from_user.id)
        await message.reply("Forward the FIRST message from the DB channel (or /cancel).")

    @app.on_message(filters.command("cancel") & filters.private & admin_only)
    async def cancel_handler(_client: Client, message) -> None:
        state.cancel(message.from_user.id)
        await message.reply("Cancelled.")

    @app.on_message(filters.private & admin_only & ~filters.command(["start", "help", "batch", "cancel"]))
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
