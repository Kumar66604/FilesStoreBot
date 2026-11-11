"""Private user-facing handlers."""

import asyncio
import time
from datetime import datetime, timezone

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ..config import Settings
from ..services.files import FileService
from ..services.force_subscriptions import ForceSubscriptionService
from ..services.links import LinkService
from ..services.subscriptions import SubscriptionService


def register_user_handlers(
    app: Client,
    settings: Settings,
    users,
    links: LinkService,
    files: FileService,
    subscriptions: SubscriptionService,
    force_subscriptions: ForceSubscriptionService,
) -> None:
    async def require_force_subscription(client: Client, message) -> bool:
        if message.from_user.id in settings.admins or await force_subscriptions.is_allowed(client, message.from_user.id):
            return True
        await message.reply(
            "Please join or request to join all required chats before using this bot.",
            reply_markup=await force_subscriptions.keyboard(),
        )
        return False

    @app.on_chat_join_request()
    async def chat_join_request_handler(_client: Client, request) -> None:
        if request.from_user:
            await force_subscriptions.record_join_request(request.chat.id, request.from_user.id)

    @app.on_callback_query(filters.regex(r"^forcesub:check$"))
    async def force_subscription_check_handler(client: Client, query) -> None:
        if await force_subscriptions.is_allowed(client, query.from_user.id):
            await query.answer("Access confirmed. You can use the bot now.", show_alert=True)
        else:
            await query.answer("You still need to join/request every required chat.", show_alert=True)

    @app.on_message(filters.command("start") & filters.private)
    async def start_handler(client: Client, message) -> None:
        await users.update_one(
            {"_id": message.from_user.id},
            {"$set": {"name": message.from_user.first_name}},
            upsert=True,
        )
        if not await require_force_subscription(client, message):
            return
        if len(message.command) < 2:
            await message.reply(
                f"Welcome to FilesStore, {message.from_user.first_name}!\n\n"
                "Your private file delivery assistant. Open a file link from this bot to receive your files, "
                "or explore the menu below.",
                reply_markup=_welcome_keyboard(),
            )
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
                "Your free allowance has been used.\n\nChoose a plan to continue downloading:",
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
        if not await require_force_subscription(_client, message):
            return
        await message.reply(
            _help_home(settings),
            reply_markup=_help_keyboard(),
        )

    @app.on_callback_query(filters.regex(r"^help:(home|files|payments|commands)$"))
    async def help_section_handler(_client: Client, query) -> None:
        section = query.matches[0].group(1)
        await query.answer()
        text = {
            "home": _help_home(settings),
            "files": _help_files(settings),
            "payments": _help_payments(settings),
            "commands": _help_commands(),
        }[section]
        await query.message.edit_text(text, reply_markup=_help_keyboard(section))

    @app.on_callback_query(filters.regex(r"^plans:(back|open)$"))
    async def plans_back_handler(_client: Client, query) -> None:
        await query.answer()
        await query.message.edit_text(
            "Choose a plan to continue:",
            reply_markup=await _pack_keyboard(subscriptions),
        )

    @app.on_callback_query(filters.regex(r"^pack:([a-z0-9_-]+)$"))
    async def pack_handler(_client: Client, query) -> None:
        if query.from_user.id not in settings.admins and not await force_subscriptions.is_allowed(_client, query.from_user.id):
            await query.answer("Join/request all required chats first.", show_alert=True)
            return
        pack = await subscriptions.get_pack(query.matches[0].group(1))
        await query.answer()
        if not pack:
            await query.message.reply("That subscription pack is no longer available. Please try again.")
            return
        await query.message.reply(
            f"{pack['name']}\n"
            f"{pack['days']} days  •  {pack['stars']} Stars\n\n"
            "Choose a payment method:",
            reply_markup=_method_keyboard(pack, await subscriptions.list_upi_accounts()),
        )

    @app.on_callback_query(filters.regex(r"^pay:([a-z0-9_-]+):(stars|upi)$"))
    async def payment_option_handler(client: Client, query) -> None:
        if query.from_user.id not in settings.admins and not await force_subscriptions.is_allowed(client, query.from_user.id):
            await query.answer("Join/request all required chats first.", show_alert=True)
            return
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
                f"{pack['name']}  •  Rs {pack['upi_amount']}\n\n"
                "Choose a UPI account:",
                reply_markup=_upi_keyboard(pack_id, accounts),
            )
            return
        await query.message.reply(
            "Tap the button below to open the secure payment page. After payment, return here to download your files.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton(
                    "Continue to Stars payment",
                    url=f"https://t.me/{settings.payment_bot_username}?start=pay_{pack_id}",
                )]]
            ),
        )

    @app.on_callback_query(filters.regex(r"^upi:([a-z0-9_-]+):([a-z0-9_-]+)$"))
    async def upi_account_handler(_client: Client, query) -> None:
        if query.from_user.id not in settings.admins and not await force_subscriptions.is_allowed(_client, query.from_user.id):
            await query.answer("Join/request all required chats first.", show_alert=True)
            return
        pack_id, account_id = query.matches[0].groups()
        pack = await subscriptions.get_pack(pack_id)
        account = await subscriptions.get_upi_account(account_id)
        await query.answer()
        if not pack or not account:
            await query.message.reply("That pack or UPI account is no longer available. Please try again.")
            return
        await query.message.reply(
            f"UPI payment\n\n"
            f"Amount: Rs {pack['upi_amount']}\n"
            f"Account: {account['label']}\n"
            f"UPI ID: `{account['upi_id']}`\n\n"
            "After completing the transfer, submit your UTR using:\n"
            f"`/upi {pack_id} {account_id} YOUR_UTR_NUMBER`\n\n"
            "Your subscription will activate after admin verification.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Choose another UPI account", callback_data=f"upichoose:{pack_id}")]]
            ),
        )

    @app.on_callback_query(filters.regex(r"^upichoose:([a-z0-9_-]+)$"))
    async def choose_upi_handler(_client: Client, query) -> None:
        if query.from_user.id not in settings.admins and not await force_subscriptions.is_allowed(_client, query.from_user.id):
            await query.answer("Join/request all required chats first.", show_alert=True)
            return
        pack_id = query.matches[0].group(1)
        pack = await subscriptions.get_pack(pack_id)
        await query.answer()
        if not pack:
            await query.message.reply("That subscription pack is no longer available. Please try again.")
            return
        await query.message.reply(
            f"{pack['name']}  •  Rs {pack['upi_amount']}\n\nChoose another UPI account:",
            reply_markup=_upi_keyboard(pack_id, await subscriptions.list_upi_accounts()),
        )

    @app.on_message(filters.command("upi") & filters.private)
    async def upi_reference_handler(client: Client, message) -> None:
        if not await require_force_subscription(client, message):
            return
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
                reply_markup=InlineKeyboardMarkup(
                    [[
                        InlineKeyboardButton("Approve", callback_data=f"upireview:approve:{message.from_user.id}"),
                        InlineKeyboardButton("Decline", callback_data=f"upireview:decline:{message.from_user.id}"),
                    ]]
                ),
            )
        await message.reply("Your payment reference was sent for verification. Please wait for approval.")


async def _pack_keyboard(subscriptions: SubscriptionService) -> InlineKeyboardMarkup:
    packs = await subscriptions.list_packs()
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(
                f"{pack['name']}  •  {pack['days']} days  •  {pack['stars']} Stars",
                callback_data=f"pack:{pack['id']}",
            )]
            for pack in packs
        ]
    )


def _method_keyboard(pack: dict, accounts: list[dict]) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton("Pay with Telegram Stars", callback_data=f"pay:{pack['id']}:stars")]]
    if accounts:
        buttons.append([InlineKeyboardButton("Pay with UPI", callback_data=f"pay:{pack['id']}:upi")])
    buttons.append([InlineKeyboardButton("Back to plans", callback_data="plans:back")])
    return InlineKeyboardMarkup(buttons)


def _upi_keyboard(pack_id: str, accounts: list[dict]) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(account["label"], callback_data=f"upi:{pack_id}:{account['id']}")]
        for account in accounts
    ]
    buttons.append([InlineKeyboardButton("Back to payment methods", callback_data=f"pack:{pack_id}")])
    return InlineKeyboardMarkup(buttons)


def _welcome_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("How it works", callback_data="help:files")],
        [InlineKeyboardButton("Plans & payment", callback_data="plans:open")],
        [InlineKeyboardButton("Help & commands", callback_data="help:commands")],
    ])


def _help_keyboard(active: str = "home") -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("How it works", callback_data="help:files"),
            InlineKeyboardButton("Plans & payment", callback_data="help:payments"),
        ],
        [InlineKeyboardButton("Commands", callback_data="help:commands")],
    ]
    if active != "home":
        buttons.append([InlineKeyboardButton("Help home", callback_data="help:home")])
    if active == "payments":
        buttons.append([InlineKeyboardButton("View available plans", callback_data="plans:open")])
    return InlineKeyboardMarkup(buttons)


def _help_home(settings: Settings) -> str:
    quota = (
        f"Your first {settings.free_files} files are free."
        if settings.free_files
        else "Access is subscription-based."
    )
    return (
        "FilesStore Help\n\n"
        "Store owners share a file link with you, and FilesStore delivers the files privately.\n\n"
        f"{quota} After that, choose a plan and pay with Telegram Stars or UPI."
    )


def _help_files(settings: Settings) -> str:
    delete_note = (
        f"Files are automatically deleted after {settings.auto_delete_seconds // 60} minutes. Save them before then."
        if settings.auto_delete_seconds
        else "Automatic deletion is currently disabled."
    )
    return (
        "How it works\n\n"
        "1. Open a file link sent by this bot.\n"
        "2. Complete the access check if requested.\n"
        "3. Files are delivered directly in this private chat.\n\n"
        f"{delete_note}"
    )


def _help_payments(settings: Settings) -> str:
    if not settings.subscription_days:
        return "Plans & payment\n\nSubscription plans are currently unavailable."
    return (
        "Plans & payment\n\n"
        "After your free allowance is used, choose a subscription plan.\n\n"
        "Telegram Stars: instant activation after Telegram confirms payment.\n"
        "UPI: send the amount, submit the UTR, and wait for admin verification.\n\n"
        "Your active plan extends from its current expiry date when you renew."
    )


def _help_commands() -> str:
    return (
        "User commands\n\n"
        "/start - Open a file link or show the welcome menu\n"
        "/help - Open this guided help\n"
        "/upi PACK_ID ACCOUNT_ID UTR - Submit a UPI payment reference\n\n"
        "Tip: use the buttons in the bot messages whenever possible. They keep your plan and payment details selected correctly."
    )


async def _delete_later(messages, delay: int) -> None:
    await asyncio.sleep(delay)
    for message in messages:
        try:
            await message.delete()
        except Exception:
            continue
