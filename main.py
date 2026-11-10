"""Run the Telegram file store bot."""

from filestore_bot.app import create_app
from filestore_bot.config import Settings
from filestore_bot.health import start_health_server


def main() -> None:
    settings = Settings.from_env()
    settings.validate()
    start_health_server(settings.port)
    create_app(settings).run()


if __name__ == "__main__":
    main()
