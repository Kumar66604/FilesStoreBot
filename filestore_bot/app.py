"""Application factory and dependency wiring."""

from pyrogram import Client

from .config import Settings
from .database import create_database
from .handlers.admin import register_admin_handlers
from .handlers.user import register_user_handlers
from .services.files import FileService
from .services.force_subscriptions import ForceSubscriptionService
from .services.links import LinkService
from .services.subscriptions import SubscriptionService
from .state import BatchState


def create_app(settings: Settings) -> Client:
    app, _subscriptions = create_app_with_services(settings)
    return app


def create_app_with_services(settings: Settings) -> tuple[Client, SubscriptionService]:
    app = Client(
        "filestore",
        api_id=settings.api_id,
        api_hash=settings.api_hash,
        bot_token=settings.bot_token,
        workers=settings.workers,
        in_memory=True,
    )
    database = create_database(settings)
    users = database.users
    links = LinkService(settings)
    files = FileService(settings)
    subscriptions = SubscriptionService(database, settings)
    force_subscriptions = ForceSubscriptionService(database)
    register_user_handlers(app, settings, users, links, files, subscriptions, force_subscriptions)
    register_admin_handlers(app, settings, links, files, BatchState(), subscriptions, force_subscriptions)
    return app, subscriptions
