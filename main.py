"""Run the Telegram file store bot."""

import asyncio

from pyrogram import idle

from filestore_bot.app import create_app_with_services
from filestore_bot.config import Settings
from filestore_bot.health import start_health_server


def main() -> None:
    settings = Settings.from_env()
    settings.validate()
    start_health_server(settings.port)
    app, subscriptions = create_app_with_services(settings)
    app.run(_run_app(app, subscriptions))


async def _run_app(app, subscriptions) -> None:
    await app.start()
    expiry_task = asyncio.create_task(subscriptions.expiry_notification_loop(app))
    try:
        await idle()
    finally:
        expiry_task.cancel()
        await asyncio.gather(expiry_task, return_exceptions=True)
        await app.stop()


if __name__ == "__main__":
    main()
