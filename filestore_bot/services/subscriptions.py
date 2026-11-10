"""Free-download limits and subscription entitlements."""

from datetime import datetime, timedelta, timezone
import re

from ..config import Settings


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class SubscriptionService:
    def __init__(self, database, settings: Settings) -> None:
        self._users = database.users
        self._subscriptions = database.subscriptions
        self._payments = database.payments
        self._packs = database.subscription_packs
        self._upi_accounts = database.upi_accounts
        self._app_settings = database.app_settings
        self._settings = settings

    async def _get_subscription(self, user_id: int) -> dict | None:
        document = await self._subscriptions.find_one({"_id": user_id})
        if document:
            return document
        legacy = await self._users.find_one(
            {"_id": user_id},
            {"free_files_used": 1, "subscription_until": 1, "subscription_method": 1, "star_charge_ids": 1},
        )
        if not legacy or not any(
            key in legacy for key in ("free_files_used", "subscription_until", "subscription_method", "star_charge_ids")
        ):
            return None
        migrated = {"_id": user_id}
        migrated.update({key: value for key, value in legacy.items() if key != "_id"})
        await self._subscriptions.insert_one(migrated)
        await self._users.update_one(
            {"_id": user_id},
            {"$unset": {
                "free_files_used": "",
                "subscription_until": "",
                "subscription_method": "",
                "star_charge_ids": "",
            }},
        )
        return migrated

    async def list_packs(self) -> list[dict]:
        document = await self._packs.find_one({"_id": "catalog"})
        if not document:
            legacy = await self._users.find_one({"_id": "config:subscription_packs"})
            if legacy and legacy.get("items"):
                await self._packs.update_one(
                    {"_id": "catalog"}, {"$set": {"items": legacy["items"]}}, upsert=True
                )
                await self._users.delete_one({"_id": "config:subscription_packs"})
                document = legacy
        if document and document.get("items"):
            return document["items"]
        default = {
            "id": "default",
            "name": "Default",
            "stars": self._settings.subscription_stars,
            "days": self._settings.subscription_days,
            "upi_amount": self._settings.upi_amount,
        }
        await self._packs.update_one(
            {"_id": "catalog"},
            {"$set": {"items": [default]}},
            upsert=True,
        )
        return [default]

    async def get_pack(self, pack_id: str) -> dict | None:
        return next((pack for pack in await self.list_packs() if pack["id"] == pack_id), None)

    async def add_pack(self, pack_id: str, name: str, stars: int, days: int, upi_amount: str) -> dict:
        if not re.fullmatch(r"[a-z0-9_-]{1,24}", pack_id):
            raise ValueError("Pack ID must use lowercase letters, numbers, _ or - (max 24 characters).")
        packs = await self.list_packs()
        if any(pack["id"] == pack_id for pack in packs):
            raise ValueError("That pack ID already exists.")
        if stars <= 0 or days <= 0 or not upi_amount:
            raise ValueError("Stars and days must be positive, and UPI amount is required.")
        pack = {"id": pack_id, "name": name, "stars": stars, "days": days, "upi_amount": upi_amount}
        packs.append(pack)
        await self._packs.update_one({"_id": "catalog"}, {"$set": {"items": packs}}, upsert=True)
        return pack

    async def delete_pack(self, pack_id: str) -> bool:
        packs = await self.list_packs()
        remaining = [pack for pack in packs if pack["id"] != pack_id]
        if len(remaining) == len(packs):
            return False
        if not remaining:
            raise ValueError("Keep at least one subscription pack.")
        await self._packs.update_one({"_id": "catalog"}, {"$set": {"items": remaining}}, upsert=True)
        return True

    async def list_upi_accounts(self) -> list[dict]:
        document = await self._upi_accounts.find_one({"_id": "catalog"})
        if not document:
            legacy = await self._users.find_one({"_id": "config:upi_accounts"})
            if legacy and legacy.get("items"):
                await self._upi_accounts.update_one(
                    {"_id": "catalog"}, {"$set": {"items": legacy["items"]}}, upsert=True
                )
                await self._users.delete_one({"_id": "config:upi_accounts"})
                document = legacy
        if document and document.get("items"):
            return document["items"]
        if not self._settings.upi_id:
            return []
        default = {"id": "default", "label": "Default", "upi_id": self._settings.upi_id}
        await self._upi_accounts.update_one(
            {"_id": "catalog"},
            {"$set": {"items": [default]}},
            upsert=True,
        )
        return [default]

    async def get_upi_account(self, account_id: str) -> dict | None:
        return next((account for account in await self.list_upi_accounts() if account["id"] == account_id), None)

    async def add_upi_account(self, account_id: str, label: str, upi_id: str) -> dict:
        if not re.fullmatch(r"[a-z0-9_-]{1,24}", account_id):
            raise ValueError("UPI account ID must use lowercase letters, numbers, _ or - (max 24 characters).")
        accounts = await self.list_upi_accounts()
        if any(account["id"] == account_id for account in accounts):
            raise ValueError("That UPI account ID already exists.")
        account = {"id": account_id, "label": label, "upi_id": upi_id}
        accounts.append(account)
        await self._upi_accounts.update_one({"_id": "catalog"}, {"$set": {"items": accounts}}, upsert=True)
        return account

    async def delete_upi_account(self, account_id: str) -> bool:
        accounts = await self.list_upi_accounts()
        remaining = [account for account in accounts if account["id"] != account_id]
        if len(remaining) == len(accounts):
            return False
        await self._upi_accounts.update_one({"_id": "catalog"}, {"$set": {"items": remaining}}, upsert=True)
        return True

    async def is_enabled(self) -> bool:
        document = await self._app_settings.find_one({"_id": "subscription"})
        if not document:
            legacy = await self._users.find_one({"_id": "config:subscription_settings"})
            if legacy and "enabled" in legacy:
                await self._app_settings.update_one(
                    {"_id": "subscription"}, {"$set": {"enabled": legacy["enabled"]}}, upsert=True
                )
                await self._users.delete_one({"_id": "config:subscription_settings"})
                document = legacy
        return document.get("enabled", True) if document else True

    async def set_enabled(self, enabled: bool) -> None:
        await self._app_settings.update_one(
            {"_id": "subscription"},
            {"$set": {"enabled": enabled}},
            upsert=True,
        )

    async def can_download(self, user_id: int, file_count: int) -> bool:
        if not await self.is_enabled():
            return True
        user = await self._get_subscription(user_id)
        expiry = _as_utc(user.get("subscription_until")) if user else None
        if expiry and expiry > _utc_now():
            return True
        used = int(user.get("free_files_used", 0)) if user else 0
        return used + file_count <= self._settings.free_files

    async def record_free_downloads(self, user_id: int, file_count: int) -> None:
        if not await self.is_enabled():
            return
        await self._subscriptions.update_one(
            {"_id": user_id},
            {"$inc": {"free_files_used": file_count}},
            upsert=True,
        )

    async def activate(
        self,
        user_id: int,
        method: str,
        duration_days: int,
        charge_id: str | None = None,
    ) -> datetime:
        now = _utc_now()
        user = await self._get_subscription(user_id)
        if charge_id and await self._payments.find_one({"_id": charge_id}):
            return _as_utc(user.get("subscription_until")) if user else now

        current = _as_utc(user.get("subscription_until")) if user else None
        start = current if current and current > now else now
        expiry = start + timedelta(days=duration_days)
        update = {
            "$set": {
                "subscription_until": expiry,
                "subscription_method": method,
            }
        }
        if charge_id:
            update["$addToSet"] = {"star_charge_ids": charge_id}
        await self._subscriptions.update_one({"_id": user_id}, update, upsert=True)
        if charge_id:
            await self._payments.update_one(
                {"_id": charge_id},
                {"$set": {"user_id": user_id, "kind": "telegram_stars", "created_at": now}},
                upsert=True,
            )
        return expiry

    async def save_upi_pending(self, user_id: int, pack_id: str, account_id: str, utr: str) -> None:
        await self._payments.update_one(
            {"_id": f"upi:{user_id}"},
            {"$set": {"user_id": user_id, "kind": "upi", "status": "pending", "pack_id": pack_id, "account_id": account_id, "utr": utr}},
            upsert=True,
        )

    async def get_upi_pending(self, user_id: int) -> dict | None:
        payment = await self._payments.find_one({"_id": f"upi:{user_id}", "status": "pending"})
        if payment:
            return payment
        legacy = await self._users.find_one({"_id": user_id}, {"upi_pending": 1})
        if not legacy or not legacy.get("upi_pending"):
            return None
        pending = legacy["upi_pending"]
        await self.save_upi_pending(user_id, pending["pack_id"], pending["account_id"], pending["utr"])
        await self._users.update_one({"_id": user_id}, {"$unset": {"upi_pending": ""}})
        return await self._payments.find_one({"_id": f"upi:{user_id}", "status": "pending"})

    async def clear_upi_pending(self, user_id: int) -> None:
        await self._payments.delete_one({"_id": f"upi:{user_id}"})

    async def cancel(self, user_id: int) -> bool:
        result = await self._subscriptions.update_one(
            {"_id": user_id, "subscription_until": {"$exists": True}},
            {"$unset": {"subscription_until": "", "subscription_method": ""}},
        )
        return result.modified_count > 0

    async def free_status(self, user_id: int) -> tuple[int, datetime | None]:
        user = await self._get_subscription(user_id)
        if not user:
            return 0, None
        return int(user.get("free_files_used", 0)), _as_utc(user.get("subscription_until"))
