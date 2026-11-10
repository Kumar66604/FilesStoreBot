# FilesStoreBot

A modular Telegram bot for storing files in a private channel and delivering
them through compact deep links.

## Project structure

```text
main.py                  Application entry point
filestore_bot/
  app.py                 Pyrogram app and dependency wiring
  config.py              Environment-backed settings
  database.py            MongoDB connection setup
  health.py              Hosting-platform health endpoint
  encoding.py            Deep-link encoding helpers
  state.py               In-memory admin batch state
  handlers/              Telegram message handlers
  services/              File delivery and link services
```

## Environment variables

`API_ID`, `API_HASH`, `BOT_TOKEN`, `DB_CHANNEL`, and `ADMINS` are required.
`DB_URI`, `DB_NAME`, `WORKERS`, `AUTO_DEL`, `PROTECT`, and `PORT` are optional
and keep the previous defaults.

Run it with:

```bash
python main.py
```

Admins can send media directly to the bot to store it, or use `/batch` and
forward the first and last messages from the storage channel to create a range
link. Users open the generated `/start` link to receive the files.
