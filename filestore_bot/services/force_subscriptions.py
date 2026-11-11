"""Force-subscription configuration and Telegram membership checks."""

from datetime import datetime, timezone

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup


class ForceSubscriptionService:
    """Manage chats users must join before using the bot."""

    def __init__(self, database) -> None:
        self._collection = database.force_subscriptions

    async def list(self) -> list[dict]:
        forces = []
        async for force in self._collection.find({}).sort("created_at", 1):
            forces.append(force)
        return forces

    async def add(self, client, chat_id: int, mode: str, label: str = "") -> dict:
        if mode not in {"join", "request"}:
            raise ValueError("Mode must be join or request.")
        chat = await client.get_chat(chat_id)
        chat_title = label.strip() or getattr(chat, "title", None) or str(chat_id)
        username = getattr(chat, "username", None)
        if username and mode == "join":
            link = f"https://t.me/{username}"
        else:
            invite = await client.create_chat_invite_link(
                chat_id,
                name="FilesStore force subscription",
                creates_join_request=mode == "request",
            )
            link = invite.invite_link
        document = {
            "_id": chat_id,
            "chat_id": chat_id,
            "title": chat_title,
            "mode": mode,
            "link": link,
            "requested_users": [],
            "created_at": datetime.now(timezone.utc),
        }
        await self._collection.replace_one({"_id": chat_id}, document, upsert=True)
        return document

    async def remove(self, chat_id: int) -> bool:
        result = await self._collection.delete_one({"_id": chat_id})
        return result.deleted_count > 0

    async def is_allowed(self, client, user_id: int) -> bool:
        for force in await self.list():
            if force.get("mode") == "request" and user_id in force.get("requested_users", []):
                continue
            try:
                member = await client.get_chat_member(force["chat_id"], user_id)
            except Exception:
                return False
            raw_status = getattr(member, "status", "")
            # Pyrogram returns a string, while Kurigram/client variants may
            # return ChatMemberStatus.MEMBER-style enum values.
            status = getattr(raw_status, "value", raw_status)
            status = str(status).lower().rsplit(".", 1)[-1]
            if status in {"member", "administrator", "owner"}:
                continue
            if status == "restricted" and bool(getattr(member, "is_member", False)):
                continue
            return False
        return True

    async def record_join_request(self, chat_id: int, user_id: int) -> bool:
        result = await self._collection.update_one(
            {"_id": chat_id, "mode": "request"},
            {"$addToSet": {"requested_users": user_id}},
        )
        return result.matched_count > 0

    async def keyboard(self) -> InlineKeyboardMarkup | None:
        forces = await self.list()
        if not forces:
            return None
        buttons = [
            [InlineKeyboardButton(
                f"{'Request to join' if force.get('mode') == 'request' else 'Join'}: {force.get('title', force['chat_id'])}",
                url=force["link"],
            )]
            for force in forces
        ]
        buttons.append([InlineKeyboardButton("✅ I joined / requested", callback_data="forcesub:check")])
        return InlineKeyboardMarkup(buttons)

