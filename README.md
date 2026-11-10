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

MongoDB data is separated into `users`, `subscriptions`, `payments`,
`subscription_packs`, `upi_accounts`, and `app_settings` collections. Existing
legacy configuration and entitlement fields are migrated automatically when
they are first accessed.

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

Admins can manage payment options and subscription enforcement from the bot:

```text
/addpack ID STARS DAYS UPI_AMOUNT [NAME]
/listpacks
/delpack ID
/addupi ID UPI_ID [LABEL]
/listupi
/delupi ID
/submode on|off|status
/cancelsub USER_ID
/link                 # reply to any text or media message
```

Users select a pack first, then Stars or UPI, and finally a specific UPI
account. The selected values are stored with the pending payment before the
payment process starts.

Users with an active subscription receive one reminder per day when 3, 2, and
1 day remain before expiry. Notification delivery is tracked so each reminder
is sent only once per subscription expiry.

To create a link for a text message, an admin replies `/link` to that message.
The same command works for media messages; direct media uploads to the bot also
continue to generate links.

Run it with:

```bash
python main.py
```

Admins can send media directly to the bot to store it, or use `/batch` and
forward the first and last messages from the storage channel to create a range
link. Users open the generated `/start` link to receive the files.
