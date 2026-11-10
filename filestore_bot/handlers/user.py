"""Private user-facing handlers."""

import asyncio
import time
from datetime import datetime, timezone

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice

from ..config import Settings
from ..services.files import FileService
from ..services.links import LinkService
from ..services.subscriptions import SubscriptionService


def register_user_handlers(
    app: Client,
    settings: Settings,
    users,
    links: LinkService,
    files: FileService,
    subscriptions: SubscriptionService,
) -> None:
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
        requested = last - first + 1
        if message.from_user.id not in settings.admins and not await subscriptions.can_download(
            message.from_user.id, requested
        ):
            await message.reply(
                f"Your {settings.free_files} free files are finished. Choose a subscription pack:",
                reply_markup=await _pack_keyboard(subscriptions),
            )
            return
        sent = await files.deliver(client, settings.db_channel, message.chat.id, first, last)
        if not sent:
            await message.reply("Files not found.")
            return
        if message.from_user.id not in settings.admins:
            _, expiry = await subscriptions.free_status(message.from_user.id)
            if not expiry or expiry <= datetime.now(timezone.utc):
                await subscriptions.record_free_downloads(message.from_user.id, len(sent))
        if settings.auto_delete_seconds:
            note = await message.reply(
                f"These files will be deleted in {settings.auto_delete_seconds // 60} min. Save them now."
            )
            asyncio.create_task(_delete_later(sent + [note], settings.auto_delete_seconds))

    @app.on_message(filters.command("help") & filters.private & ~filters.user(settings.admins))
    async def user_help_handler(_client: Client, message) -> None:
        await message.reply(
            "FilesStore Bot help\n\n"
            "Open a file link sent by this bot to receive your files. "
            f"The first {settings.free_files} files are free. After that, choose a subscription pack, "
            "then pay with Telegram Stars or a configured UPI account.\n\n"
            "Commands:\n"
            "/start - Open a file link or show the welcome message\n"
            "/help - Show this help\n"
            "/upi PACK_ID UPI_ACCOUNT_ID UTR - Submit a UPI payment reference\n\n"
            "UPI payments are checked manually by an admin. Never submit a UPI reference until your payment is complete."
        )

    @app.on_callback_query(filters.regex(r"^pack:([a-z0-9_-]+)$"))
    async def pack_handler(_client: Client, query) -> None:
        pack = await subscriptions.get_pack(query.matches[0].group(1))
        await query.answer()
        if not pack:
            await query.message.reply("That subscription pack is no longer available. Please try again.")
            return
        await query.message.reply(
            f"{pack['name']} - {pack['days']} days\nChoose a payment method:",
            reply_markup=_method_keyboard(pack, await subscriptions.list_upi_accounts()),
        )

    @app.on_callback_query(filters.regex(r"^pay:([a-z0-9_-]+):(stars|upi)$"))
    async def payment_option_handler(client: Client, query) -> None:
        pack_id, option = query.matches[0].groups()
        pack = await subscriptions.get_pack(pack_id)
        await query.answer()
        if not pack:
            await query.message.reply("That subscription pack is no longer available. Please try again.")
            return
        if option == "upi":
            accounts = await subscriptions.list_upi_accounts()
            if not accounts:
                await query.message.reply("UPI payments are not configured yet.")
                return
            await query.message.reply(
                f"{pack['name']} - Rs {pack['upi_amount']}\nChoose which UPI account to use:",
                reply_markup=_upi_keyboard(pack_id, accounts),
            )
            return
        payload = f"subscription:{pack_id}:{query.from_user.id}:{int(time.time())}"
        await client.send_invoice(
            chat_id=query.from_user.id,
            title="FilesStore subscription",
            description=f"{pack['days']} days of unlimited file downloads",
            payload=payload,
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(pack["name"], pack["stars"])],
        )

    @app.on_callback_query(filters.regex(r"^upi:([a-z0-9_-]+):([a-z0-9_-]+)$"))
    async def upi_account_handler(_client: Client, query) -> None:
        pack_id, account_id = query.matches[0].groups()
        pack = await subscriptions.get_pack(pack_id)
        account = await subscriptions.get_upi_account(account_id)
        await query.answer()
        if not pack or not account:
            await query.message.reply("That pack or UPI account is no longer available. Please try again.")
            return
        await query.message.reply(
            f"UPI payment\n\nSend Rs {pack['upi_amount']} to {account['label']}:\n`{account['upi_id']}`\n\n"
            f"After payment, send:\n`/upi {pack_id} {account_id} YOUR_UTR_NUMBER`\n\n"
            "An admin will verify it and activate your subscription.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Choose another UPI account", callback_data=f"upichoose:{pack_id}")]]
            ),
        )

    @app.on_callback_query(filters.regex(r"^upichoose:([a-z0-9_-]+)$"))
    async def choose_upi_handler(_client: Client, query) -> None:
        pack_id = query.matches[0].group(1)
        pack = await subscriptions.get_pack(pack_id)
        await query.answer()
        if not pack:
            await query.message.reply("That subscription pack is no longer available. Please try again.")
            return
        await query.message.reply(
            f"{pack['name']} - Rs {pack['upi_amount']}\nChoose another UPI account:",
            reply_markup=_upi_keyboard(pack_id, await subscriptions.list_upi_accounts()),
        )

    @app.on_pre_checkout_query()
    async def pre_checkout_handler(query) -> None:
        valid = query.invoice_payload.startswith("subscription:") and query.currency == "XTR"
        if valid:
            parts = query.invoice_payload.split(":")
            pack = await subscriptions.get_pack(parts[1]) if len(parts) == 4 else None
            valid = bool(
                pack
                and str(query.from_user.id) == parts[2]
                and query.total_amount == pack["stars"]
            )
        await query.answer(ok=valid, error_message=None if valid else "This subscription invoice is no longer valid.")

    @app.on_message(filters.successful_payment & filters.private)
    async def successful_payment_handler(_client: Client, message) -> None:
        payment = message.successful_payment
        parts = payment.invoice_payload.split(":")
        pack = await subscriptions.get_pack(parts[1]) if len(parts) == 4 else None
        if (
            payment.currency != "XTR"
            or not pack
            or str(message.from_user.id) != parts[2]
            or payment.total_amount != pack["stars"]
        ):
            await message.reply("Payment received, but the invoice amount could not be verified. Contact an admin.")
            return
        expiry = await subscriptions.activate(
            message.from_user.id,
            "telegram_stars",
            pack["days"],
            payment.telegram_payment_charge_id,
        )
        await message.reply(f"Payment successful. Your subscription is active until {expiry:%Y-%m-%d %H:%M} UTC.")

    @app.on_message(filters.command("upi") & filters.private)
    async def upi_reference_handler(client: Client, message) -> None:
        if len(message.command) < 4:
            await message.reply("Usage: `/upi PACK_ID UPI_ACCOUNT_ID UTR_NUMBER`")
            return
        pack_id, account_id, utr = [part.strip() for part in message.command[1:4]]
        pack = await subscriptions.get_pack(pack_id)
        account = await subscriptions.get_upi_account(account_id)
        if not pack or not account or not utr:
            await message.reply("Invalid pack, UPI account, or UTR. Open the payment menu again.")
            return
        await subscriptions.save_upi_pending(message.from_user.id, pack_id, account_id, utr)
        for admin_id in settings.admins:
            await client.send_message(
                admin_id,
                f"UPI payment proof received\nUser: `{message.from_user.id}`\n"
                f"Pack: `{pack_id}`\nAccount: `{account_id}`\nUTR: `{utr}`\n\n"
                f"Verify the payment and use `/approve {message.from_user.id}`.",
            )
        await message.reply("Your payment reference was sent for verification. Please wait for approval.")


async def _pack_keyboard(subscriptions: SubscriptionService) -> InlineKeyboardMarkup:
    packs = await subscriptions.list_packs()
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(f"{pack['name']} - {pack['days']} days", callback_data=f"pack:{pack['id']}")]
            for pack in packs
        ]
    )


def _method_keyboard(pack: dict, accounts: list[dict]) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton("Pay with Telegram Stars", callback_data=f"pay:{pack['id']}:stars")]]
    if accounts:
        buttons.append([InlineKeyboardButton("Pay with UPI", callback_data=f"pay:{pack['id']}:upi")])
    return InlineKeyboardMarkup(buttons)


def _upi_keyboard(pack_id: str, accounts: list[dict]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(account["label"], callback_data=f"upi:{pack_id}:{account['id']}")]
            for account in accounts
        ]
    )


async def _delete_later(messages, delay: int) -> None:
    await asyncio.sleep(delay)
    for message in messages:
        try:
            await message.delete()
        except Exception:
            continue
