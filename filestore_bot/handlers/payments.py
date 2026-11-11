"""Payment-bot handlers. This client runs in the same process as the main bot."""

import re

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice

from ..config import Settings
from ..services.subscriptions import SubscriptionService


def register_payment_handlers(
    app: Client, settings: Settings, subscriptions: SubscriptionService
) -> None:
    @app.on_message(filters.command("start") & filters.private)
    async def payment_start_handler(client: Client, message) -> None:
        if len(message.command) < 2 or not re.fullmatch(r"pay_[a-z0-9_-]{1,24}", message.command[1]):
            await message.reply("Please open the payment button from the main FilesStore bot.")
            return
        pack_id = message.command[1][4:]
        pack = await subscriptions.get_pack(pack_id)
        if not pack:
            await message.reply("That subscription pack is no longer available. Please return to the main bot.")
            return
        payload = f"subscription:{pack_id}:{message.from_user.id}"
        await client.send_invoice(
            chat_id=message.chat.id,
            title="FilesStore subscription",
            description=f"{pack['days']} days of unlimited file downloads",
            payload=payload,
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(pack["name"], pack["stars"])],
        )

    @app.on_pre_checkout_query()
    async def pre_checkout_handler(query) -> None:
        parts = query.invoice_payload.split(":")
        pack = await subscriptions.get_pack(parts[1]) if len(parts) == 3 else None
        valid = bool(
            pack
            and query.currency == "XTR"
            and str(query.from_user.id) == parts[2]
            and query.total_amount == pack["stars"]
        )
        await query.answer(
            ok=valid,
            error_message=None if valid else "This subscription invoice is no longer valid.",
        )

    @app.on_message(filters.successful_payment & filters.private)
    async def successful_payment_handler(_client: Client, message) -> None:
        payment = message.successful_payment
        parts = payment.invoice_payload.split(":")
        pack = await subscriptions.get_pack(parts[1]) if len(parts) == 3 else None
        if (
            payment.currency != "XTR"
            or not pack
            or str(message.from_user.id) != parts[2]
            or payment.total_amount != pack["stars"]
        ):
            await message.reply("Payment received, but it could not be verified. Please contact support.")
            return
        expiry = await subscriptions.activate(
            message.from_user.id,
            "telegram_stars",
            pack["days"],
            payment.telegram_payment_charge_id,
        )
        await message.reply(
            f"Payment successful. Your subscription is active until {expiry:%Y-%m-%d %H:%M} UTC.\n\n"
            "Return to the main bot to continue downloading.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Open FilesStore bot", url=f"https://t.me/{settings.bot_username}")]]
            ),
        )
