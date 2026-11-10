"""MongoDB setup."""

from motor.motor_asyncio import AsyncIOMotorClient

from .config import Settings


def create_users_collection(settings: Settings):
    client = AsyncIOMotorClient(settings.db_uri)
    return client[settings.db_name].users
