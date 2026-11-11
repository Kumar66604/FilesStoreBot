"""MongoDB connection and separated application collections."""

from dataclasses import dataclass

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection

from .config import Settings


@dataclass(slots=True)
class Database:
    client: AsyncIOMotorClient
    users: AsyncIOMotorCollection
    subscriptions: AsyncIOMotorCollection
    payments: AsyncIOMotorCollection
    subscription_packs: AsyncIOMotorCollection
    upi_accounts: AsyncIOMotorCollection
    app_settings: AsyncIOMotorCollection
    force_subscriptions: AsyncIOMotorCollection


def create_database(settings: Settings) -> Database:
    client = AsyncIOMotorClient(settings.db_uri)
    database = client[settings.db_name]
    return Database(
        client=client,
        users=database.users,
        subscriptions=database.subscriptions,
        payments=database.payments,
        subscription_packs=database.subscription_packs,
        upi_accounts=database.upi_accounts,
        app_settings=database.app_settings,
        force_subscriptions=database.force_subscriptions,
    )
