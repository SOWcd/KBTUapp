"""Sign the userbot's Telegram account in once and print its session string.

Run by the owner in his own terminal: it asks for the api_id, api_hash, phone and the login code, and prints a
StringSession. Nothing is written to disk. The string goes into Coolify's env as TG_SESSION (with TG_API_ID and
TG_API_HASH), never into the repo: whoever has it is signed in as that account.

    server/.venv/bin/python server/tools/userbot_login.py
"""
from getpass import getpass

from telethon.sessions import StringSession
from telethon.sync import TelegramClient

api_id = int(input("api_id: "))
api_hash = getpass("api_hash (hidden): ").strip()
with TelegramClient(StringSession(), api_id, api_hash) as client:  # asks for the phone, the code and 2FA itself
    me = client.get_me()
    print(f"\nSigned in as {me.first_name} (id {me.id}). TG_SESSION for Coolify, keep it secret:\n")
    print(client.session.save())
