import asyncio
import base64

from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import Client, filters
from pyrogram.errors import FloodWait

import config
import os, threading
from http.server import BaseHTTPRequestHandler, HTTPServer

class Ping(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
    def log_message(self, *a): pass

def serve():
    HTTPServer(("0.0.0.0", int(os.environ.get("PORT", 10000))), Ping).serve_forever()

threading.Thread(target=serve, daemon=True).start()

app = Client(
    "filestore",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN,
    workers=config.WORKERS,
)
users = AsyncIOMotorClient(config.DB_URI)[config.DB_NAME].users
admin_only = filters.user(config.ADMINS)
pending = {}  # admin_id -> {"step": "first" | "last", "first": int}
K = abs(config.DB_CHANNEL)
MAX_BATCH = 500


# ---------- helpers ----------
def encode(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")


def decode(s: str) -> str:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4)).decode()


async def make_link(client: Client, first: int, last: int | None = None) -> str:
    raw = f"get-{first * K}" if last is None or last == first else f"get-{first * K}-{last * K}"
    me = await client.get_me()
    return f"https://t.me/{me.username}?start={encode(raw)}"


async def delete_later(msgs, delay: int):
    await asyncio.sleep(delay)
    for m in msgs:
        try:
            await m.delete()
        except Exception:
            pass


# ---------- user side ----------
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    await users.update_one({"_id": message.from_user.id}, {"$set": {"name": message.from_user.first_name}}, upsert=True)

    if len(message.command) < 2:
        return await message.reply(f"Hi {message.from_user.first_name}! Open a file link to get your files.")

    try:
        parts = decode(message.command[1]).split("-")
        assert parts[0] == "get"
        start_id = int(parts[1]) // K
        end_id = int(parts[2]) // K if len(parts) > 2 else start_id
        assert 0 < start_id <= end_id and end_id - start_id < MAX_BATCH
    except Exception:
        return await message.reply("Invalid or expired link.")

    ids = list(range(start_id, end_id + 1))
    sent = []
    for i in range(0, len(ids), 100):
        try:
            batch = await client.get_messages(config.DB_CHANNEL, ids[i:i + 100])
        except FloodWait as e:
            await asyncio.sleep(e.value)
            batch = await client.get_messages(config.DB_CHANNEL, ids[i:i + 100])
        for m in batch:
            if m.empty:
                continue
            try:
                sent.append(await m.copy(message.chat.id, protect_content=config.PROTECT))
            except FloodWait as e:
                await asyncio.sleep(e.value)
                sent.append(await m.copy(message.chat.id, protect_content=config.PROTECT))
            except Exception:
                pass

    if not sent:
        return await message.reply("Files not found.")
    if config.AUTO_DEL:
        note = await message.reply(f"These files will be deleted in {config.AUTO_DEL // 60} min. Save them now.")
        asyncio.create_task(delete_later(sent + [note], config.AUTO_DEL))


# ---------- admin side ----------
@app.on_message(filters.command("batch") & filters.private & admin_only)
async def batch_cmd(client, message):
    pending[message.from_user.id] = {"step": "first"}
    await message.reply("Forward the FIRST message from the DB channel (or /cancel).")


@app.on_message(filters.command("cancel") & filters.private & admin_only)
async def cancel_cmd(client, message):
    pending.pop(message.from_user.id, None)
    await message.reply("Cancelled.")


@app.on_message(
    filters.private & admin_only & ~filters.command(["start", "batch", "cancel"])
)
async def admin_message(client, message):
    state = pending.get(message.from_user.id)

    # batch flow: expects forwards from the DB channel
    if state:
        chat = message.forward_from_chat
        if not chat or chat.id != config.DB_CHANNEL:
            return await message.reply("Please forward a message from the DB channel.")
        msg_id = message.forward_from_message_id
        if state["step"] == "first":
            state.update(step="last", first=msg_id)
            return await message.reply("Now forward the LAST message.")
        first, last = sorted((state["first"], msg_id))
        pending.pop(message.from_user.id)
        return await message.reply(f"Batch link:\n{await make_link(client, first, last)}")

    # single upload: any media sent by an admin gets stored + linked
    if message.media:
        stored = await message.copy(config.DB_CHANNEL)
        return await message.reply(f"Link:\n{await make_link(client, stored.id)}")


app.run()
