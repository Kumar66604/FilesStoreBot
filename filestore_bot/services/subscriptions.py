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
    def __init__(self, users, settings: Settings) -> None:
        self._users = users
        self._settings = settings

    async def list_packs(self) -> list[dict]:
        document = await self._users.find_one({"_id": "config:subscription_packs"})
        if document and document.get("items"):
            return document["items"]
        default = {
            "id": "default",
            "name": "Default",
            "stars": self._settings.subscription_stars,
            "days": self._settings.subscription_days,
            "upi_amount": self._settings.upi_amount,
        }
        await self._users.update_one(
            {"_id": "config:subscription_packs"},
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
        await self._users.update_one({"_id": "config:subscription_packs"}, {"$set": {"items": packs}}, upsert=True)
        return pack

    async def delete_pack(self, pack_id: str) -> bool:
        packs = await self.list_packs()
        remaining = [pack for pack in packs if pack["id"] != pack_id]
        if len(remaining) == len(packs):
            return False
        if not remaining:
            raise ValueError("Keep at least one subscription pack.")
        await self._users.update_one({"_id": "config:subscription_packs"}, {"$set": {"items": remaining}}, upsert=True)
        return True

    async def list_upi_accounts(self) -> list[dict]:
        document = await self._users.find_one({"_id": "config:upi_accounts"})
        if document and document.get("items"):
            return document["items"]
        if not self._settings.upi_id:
            return []
        default = {"id": "default", "label": "Default", "upi_id": self._settings.upi_id}
        await self._users.update_one(
            {"_id": "config:upi_accounts"},
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
        await self._users.update_one({"_id": "config:upi_accounts"}, {"$set": {"items": accounts}}, upsert=True)
        return account

    async def delete_upi_account(self, account_id: str) -> bool:
        accounts = await self.list_upi_accounts()
        remaining = [account for account in accounts if account["id"] != account_id]
        if len(remaining) == len(accounts):
            return False
        await self._users.update_one({"_id": "config:upi_accounts"}, {"$set": {"items": remaining}}, upsert=True)
        return True

    async def can_download(self, user_id: int, file_count: int) -> bool:
        user = await self._users.find_one({"_id": user_id}, {"subscription_until": 1, "free_files_used": 1})
        expiry = _as_utc(user.get("subscription_until")) if user else None
        if expiry and expiry > _utc_now():
            return True
        used = int(user.get("free_files_used", 0)) if user else 0
        return used + file_count <= self._settings.free_files

    async def record_free_downloads(self, user_id: int, file_count: int) -> None:
        await self._users.update_one(
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
        user = await self._users.find_one({"_id": user_id}, {"subscription_until": 1, "star_charge_ids": 1})
        if charge_id and user and charge_id in user.get("star_charge_ids", []):
            return _as_utc(user.get("subscription_until")) or now

        current = _as_utc(user.get("subscription_until")) if user else None
        start = current if current and current > now else now
        expiry = start + timedelta(days=duration_days)
        update = {
            "$set": {
                "subscription_until": expiry,
                "subscription_method": method,
                "upi_pending_utr": None,
            }
        }
        if charge_id:
            update["$addToSet"] = {"star_charge_ids": charge_id}
        await self._users.update_one({"_id": user_id}, update, upsert=True)
        return expiry

    async def save_upi_pending(self, user_id: int, pack_id: str, account_id: str, utr: str) -> None:
        await self._users.update_one(
            {"_id": user_id},
            {"$set": {"upi_pending": {"pack_id": pack_id, "account_id": account_id, "utr": utr}}},
            upsert=True,
        )

    async def get_upi_pending(self, user_id: int) -> dict | None:
        user = await self._users.find_one({"_id": user_id}, {"upi_pending": 1})
        return user.get("upi_pending") if user else None

    async def clear_upi_pending(self, user_id: int) -> None:
        await self._users.update_one({"_id": user_id}, {"$unset": {"upi_pending": ""}})

    async def cancel(self, user_id: int) -> bool:
        result = await self._users.update_one(
            {"_id": user_id, "subscription_until": {"$exists": True}},
            {"$unset": {"subscription_until": "", "subscription_method": ""}},
        )
        return result.modified_count > 0

    async def free_status(self, user_id: int) -> tuple[int, datetime | None]:
        user = await self._users.find_one({"_id": user_id}, {"free_files_used": 1, "subscription_until": 1})
        if not user:
            return 0, None
        return int(user.get("free_files_used", 0)), _as_utc(user.get("subscription_until"))
