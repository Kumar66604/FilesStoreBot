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

For monetization, normal users can download `FREE_FILES` files for free. After
that, the bot offers Telegram Stars and UPI. Configure these optional variables
on Render:

```text
FREE_FILES=3
SUBSCRIPTION_STARS=100
SUBSCRIPTION_DAYS=30
UPI_ID=your-upi-id@bank
UPI_AMOUNT=99
```

Telegram Stars activate automatically after successful payment. UPI payments
are manual: the user selects a pack and UPI account, sends `/upi PACK_ID
UPI_ACCOUNT_ID UTR_NUMBER`, an admin verifies the payment, then runs
`/approve USER_ID`.

Admins can manage payment options from the bot:

```text
/addpack ID STARS DAYS UPI_AMOUNT [NAME]
/listpacks
/delpack ID
/addupi ID UPI_ID [LABEL]
/listupi
/delupi ID
```

Users select a pack first, then Stars or UPI, and finally a specific UPI
account. The selected values are stored with the pending payment before the
payment process starts.

Run it with:

```bash
python main.py
```

Admins can send media directly to the bot to store it, or use `/batch` and
forward the first and last messages from the storage channel to create a range
link. Users open the generated `/start` link to receive the files.
