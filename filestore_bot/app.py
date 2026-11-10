"""Application factory and dependency wiring."""

from pyrogram import Client

from .config import Settings
from .database import create_users_collection
from .handlers.admin import register_admin_handlers
from .handlers.user import register_user_handlers
from .services.files import FileService
from .services.links import LinkService
from .state import BatchState


def create_app(settings: Settings) -> Client:
    app = Client(
        "filestore",
        api_id=settings.api_id,
        api_hash=settings.api_hash,
        bot_token=settings.bot_token,
        workers=settings.workers,
        in_memory=True,
    )
    users = create_users_collection(settings)
    links = LinkService(settings)
    files = FileService(settings)
    register_user_handlers(app, settings, users, links, files)
    register_admin_handlers(app, settings, links, files, BatchState())
    return app
