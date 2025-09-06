# MrSyD
# Telegram Channel @Bot_Cracker
# Developer @syd_xyz

import asyncio
import logging
import logging.config
import os
import re
import sys
import time as tm
import typing
import datetime

from pyrogram import Client, __version__, idle, filters, enums
from pyrogram.raw.all import layer
from pyrogram.enums import ParseMode, ChatMemberStatus, ChatType
from pyrogram.errors import FloodWait, MessageNotModified, RPCError, InputUserDeactivated, UserIsBlocked, ChannelInvalid, ChatAdminRequired, UsernameInvalid, UsernameNotModified, ChannelPrivate, PeerIdInvalid, UserAlreadyParticipant
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, Message, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove

from aiohttp import web

# =========================================================================
# CONFIGURATION
# =========================================================================

class Config:
    API_ID = os.environ.get("API_ID", "")
    API_HASH = os.environ.get("API_HASH", "")
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
    BOT_SESSION = os.environ.get("BOT_SESSION", "forward-bot")
    DB_URL = os.environ.get("DB_URL", "")
    PORT = os.environ.get("PORT", "8080")
    DB_NAME = os.environ.get("DB_NAME", "cluster0")
    OWNER_ID = [int(id) for id in os.environ.get("OWNER_ID", '').split()]

class temp(object):
    lock = {}
    CANCEL = {}
    forwardings = 0
    BANNED_USERS = []
    IS_FRWD_CHAT = []
    UNQUIFY_CHATS = {}
    UNQUIFY_STATE = {}

# =========================================================================
# DATABASE
# =========================================================================

import motor.motor_asyncio
from pymongo import MongoClient

DB_NAME = Config.DB_NAME
DB_URL = Config.DB_URL

async def mongodb_version():
    x = MongoClient(Config.DB_URL)
    mongodb_version = x.server_info()['version']
    return mongodb_version

class Database:
    def __init__(self, uri, database_name):
        self._client = motor.motor_asyncio.AsyncIOMotorClient(uri)
        self.db = self._client[database_name]
        self.bot = self.db.bots
        self.col = self.db.user
        self.nfy = self.db.notify
        self.chl = self.db.channels
    
    def new_user(self, id, name):
        return dict(
            id = id,
            name = name,
            ban_status=dict(
                is_banned=False,
                ban_reason="",
            ),
        )

    async def add_user(self, id, name):
        user = self.new_user(id, name)
        await self.col.insert_one(user)

    async def is_user_exist(self, id):
        user = await self.col.find_one({'id':int(id)})
        return bool(user)

    async def total_users_bots_count(self):
        bcount = await self.bot.count_documents({})
        count = await self.col.count_documents({})
        return count, bcount

    async def total_channels(self):
        count = await self.chl.count_documents({})
        return count

    async def remove_ban(self, id):
        ban_status = dict(
            is_banned=False,
            ban_reason=''
        )
        await self.col.update_one({'id': id}, {'$set': {'ban_status': ban_status}})

    async def ban_user(self, user_id, ban_reason="No Reason"):
        ban_status = dict(
            is_banned=True,
            ban_reason=ban_reason
        )
        await self.col.update_one({'id': user_id}, {'$set': {'ban_status': ban_status}})

    async def get_ban_status(self, id):
        default = dict(
            is_banned=False,
            ban_reason=''
        )
        user = await self.col.find_one({'id':int(id)})
        if not user:
            return default
        return user.get('ban_status', default)

    async def get_all_users(self):
        return self.col.find({})

    async def delete_user(self, user_id):
        await self.col.delete_many({'id': int(user_id)})

    async def get_banned(self):
        users = self.col.find({'ban_status.is_banned': True})
        b_users = [user['id'] async for user in users]
        return b_users

    async def update_configs(self, id, configs):
        await self.col.update_one({'id': int(id)}, {'$set': {'configs': configs}})
        
    async def get_configs(self, id):
        default = {
            'caption': None,
            'duplicate': True,
            'forward_tag': False,
            'file_size': 0,
            'size_limit': None,
            'extension': None,
            'keywords': None,
            'protect': None,
            'button': None,
            'db_uri': None,
            'forward_delay': 1.0,
            'filters': {
               'poll': True,
               'text': True,
               'audio': True,
               'voice': True,
               'video': True,
               'photo': True,
               'document': True,
               'animation': True,
               'sticker': True
            }
        }
        user = await self.col.find_one({'id':int(id)})
        if user:
            return user.get('configs', default)
        return user.get('configs', default) if 'configs' in user else default 

    async def add_bot(self, user_id, bot_data):
       if not await self.is_bot_exist(user_id, bot_data['id']):
          await self.bot.insert_one({'user_id': user_id, 'bot': bot_data})
       return True

    async def remove_bot(self, user_id, bot_id):
       await self.bot.delete_many({'user_id': int(user_id), 'bot.id': int(bot_id)})

    async def get_bot(self, user_id: int, bot_id: int):
       bot = await self.bot.find_one({'user_id': user_id, 'bot.id': bot_id})
       return bot['bot'] if bot else None

    async def get_all_bots(self, user_id: int):
       bots = self.bot.find({'user_id': user_id})
       return [b['bot'] async for b in bots]

    async def is_bot_exist(self, user_id, bot_id):
       bot = await self.bot.find_one({'user_id': user_id, 'bot.id': bot_id})
       return bool(bot)

    async def in_channel(self, user_id: int, chat_id: int) -> bool:
       channel = await self.chl.find_one({"user_id": int(user_id), "chat_id": int(chat_id)})
       return bool(channel)

    async def add_channel(self, user_id: int, chat_id: int, title, username):
       if await self.in_channel(user_id, chat_id):
           return False
       return await self.chl.insert_one({"user_id": user_id, "chat_id": chat_id, "title": title, "username": username})

    async def remove_channel(self, user_id: int, chat_id: int):
       channel = await self.in_channel(user_id, chat_id )
       if not channel:
         return False
       return await self.chl.delete_many({"user_id": int(user_id), "chat_id": int(chat_id)})

    async def get_channel_details(self, user_id: int, chat_id: int):
       return await self.chl.find_one({"user_id": int(user_id), "chat_id": int(chat_id)})

    async def get_user_channels(self, user_id: int):
       channels = self.chl.find({"user_id": int(user_id)})
       return [channel async for channel in channels]

    async def get_filters(self, user_id):
       filters = []
       filter = (await self.get_configs(user_id))['filters']
       for k, v in filter.items():
          if v == False:
            filters.append(str(k))
       return filters

    async def add_frwd(self, user_id):
       return await self.nfy.insert_one({'user_id': int(user_id)})

    async def rmve_frwd(self, user_id=0, all=False):
       data = {} if all else {'user_id': int(user_id)}
       return await self.nfy.delete_many(data)

    async def get_all_frwd(self):
       return self.nfy.find({})

db = Database(DB_URL, DB_NAME)

# =========================================================================
# TRANSLATIONS
# =========================================================================

class Translation(object):
  START_TXT = """wassup {}

<i>Personal Past Forwarding Bot</i>

<b>Click '⊛ Hᴇʟᴩ ⊛' for... Help duh...</b>"""


  HELP_TXT = """<b><u>⋈ Hᴇʟᴩ</b></u>

<b><u>≍ Aᴠᴀɪʟᴀʙʟᴇ Cᴏᴍᴍᴀɴᴅꜱ :</u></b>
⏣ __/start - Cʜᴇᴄᴋ I'ᴍ Aʟɪᴠᴇ__ 
⏣ __/forward - FᴏRᴡᴀRD Mᴇꜱꜱᴀɢᴇꜱ__
⏣ __/unequify - Dᴇʟᴇᴛᴇ Dᴜᴩʟɪᴄᴀᴛᴇ Mᴇꜱꜱᴀɢᴇꜱ Iɴ Cʜᴀɴɴᴇʟꜱ__
⏣ __/settings - CᴏɴꜰɪɢᴜRᴇ YᴏᴜR Sᴇᴛᴛɪɴɢꜱ__
⏣ __/reset - Rᴇꜱᴇᴛ YᴏᴜR Sᴇᴛᴛɪɴɢꜱ__
⏣ __/fᴏRᴡᴀRᴅᴇʟᴀʏ - Sᴇᴛ ᴀ ᴄᴜꜱᴛᴏᴍ FᴏRᴡᴀRDɪɴɢ ᴅᴇʟᴀʏ__
⏣ __/ubclist - Lɪꜱᴛ ᴀʟʟ ᴄʜᴀᴛꜱ ᴏɴ ᴀ ꜱᴇʟᴇᴄᴛᴇᴅ ᴜꜱᴇRʙᴏᴛ__

<b><u>≬≬ FᴇᴀᴛᴜRᴇꜱ :</b></u>
► __FᴏRᴡᴀRD Mᴇꜱꜱᴀɢᴇ Fʀᴏᴍ Pᴜʙʟɪᴄ Cʜᴀɴɴᴇʟ Tᴏ YᴏᴜR Cʜᴀɴɴᴇʟ Wɪᴛʜᴏᴜᴛ Aᴅᴍɪɴ PᴇRᴍɪꜱꜱɪᴏɴ. Iꜰ Tʜᴇ Cʜᴀɴɴᴇʟ Iꜱ Pʀɪᴠᴀᴛᴇ Nᴇᴇᴅ Aᴅᴍɪɴ PᴇRᴍɪꜱꜱɪᴏɴ, BᴇᴛᴇR Tᴏ Uꜱᴇ UꜱᴇRʙᴏᴛ__
► __FᴏRᴡᴀRD Mᴇꜱꜱᴀɢᴇ Fʀᴏᴍ Pʀɪᴠᴀᴛᴇ Cʜᴀɴɴᴇʟ Tᴏ YᴏᴜR Cʜᴀɴɴᴇʟ Bʏ Uꜱɪɴɢ UꜱᴇRʙᴏᴛ (UꜱᴇR Mᴜꜱᴛ Bᴇ MᴇᴍʙᴇR Iɴ TʜᴇRᴇ)__
► __Cᴜꜱᴛᴏᴍ Cᴀᴩᴛɪᴏɴ__
► __Cᴜꜱᴛᴏᴍ Bᴜᴛᴛᴏɴ__
► __SᴜᴩᴩᴏRᴛ RᴇꜱᴛRɪᴄᴛᴇᴅ Cʜᴀᴛꜱ__
► __Sᴋɪᴩ Dᴜᴩʟɪᴄᴀᴛᴇ Mᴇꜱꜱᴀɢᴇꜱ__
► __FɪʟᴛᴇR Tʏᴩᴇ Oꜰ Mᴇꜱꜱᴀɢᴇꜱ__
► __Sᴋɪᴩ Mᴇꜱꜱᴀɢᴇꜱ Bᴀꜱᴇᴅ Oɴ Exᴛᴇɴꜱɪᴏɴꜱ & KᴇʏᴡᴏRᴅ & Sɪᴢᴇ__
"""

  HOW_USE_TXT = """<b><u>⚠️ BᴇꜰᴏRᴇ FᴏRᴡᴀRᴅ :</b></u>
  
► __Aᴅᴅ A Bᴏᴛ Oʀ UꜱᴇRʙᴏᴛ__
► __Aᴅᴅ Aᴛʟᴇᴀꜱᴛ Oɴᴇ Cʜᴀᴛ Tᴏ Cʜᴀɴɴᴇʟꜱ (YᴏᴜR Bᴏᴛ/UꜱᴇRʙᴏᴛ Mᴜꜱᴛ Bᴇ Aᴅᴍɪɴ TʜᴇRᴇ)__
► __Yᴏᴜ Cᴀɴ Aᴅᴅ Cʜᴀᴛꜱ Oʀ Bᴏᴛꜱ Bʏ Uꜱɪɴɢ /settings__
► __Iꜰ Tʜᴇ **Fʀᴏᴍ Cʜᴀɴɴᴇʟ** Iꜱ Pʀɪᴠᴀᴛᴇ, YᴏᴜR UꜱᴇRʙᴏᴛ Mᴜꜱᴛ Bᴇ A MᴇᴍʙᴇR Iɴ TʜᴇRᴇ Oʀ YᴏᴜR Bᴏᴛ Mᴜꜱᴛ Bᴇ Aᴅᴍɪɴ Iɴ TʜᴇRᴇ Aʟꜱᴏ__
► __Tʜᴇɴ Uꜱᴇ /FᴏRᴡᴀRᴅ Tᴏ FᴏRᴡᴀRᴅ Mᴇꜱꜱᴀɢᴇꜱ, WʜᴇRᴇ Iᴛ Aꜱᴋ FᴏR SᴏᴜRᴄᴇ Cʜᴀᴛ Tᴏ FᴏRᴡᴀRD__"""

  ABOUT_TXT = """<b>⋉ Mʏ Nᴀᴍᴇ :</b> {}
<b>⋉ Lᴀɴɢᴜᴀɢᴇ :</b> <a>English</a>
<b>⋉ LɪʙRᴀRʏ :</b> <a>Pyrogram</a>
<b>⋉ SᴇRᴠᴇR :</b> <a>Koyeb</a>
<b>⋉ Cʜᴀɴɴᴇʟ :</b> <a href='https://t.me/norFederation'>norFᴇᴅ</a>
<b>⋉ DᴇᴠᴇʟᴏᴩᴇR :</b> <a href='https://t.me/partDevil'>partDevil</a>"""

  STATUS_TXT = """<b><u>Bᴏᴛ Sᴛᴀᴛᴜꜱ:</u></b>
  
<b>⊛ Tᴏᴛᴀʟ UꜱᴇRꜱ :</b> <code>{}</code>
<b>⚝ Tᴏᴛᴀʟ Bᴏᴛꜱ :</b> <code>{}</code>
<b>❉ FᴏRᴡᴀRDɪɴɢ :</b> <code>{}</code>
"""

  FROM_MSG = "<b><u>Sᴇᴛ SᴏᴜRᴄᴇ Cʜᴀᴛ</u></b>\n\nFᴏRᴡᴀRD Tʜᴇ Lᴀꜱᴛ Mᴇꜱꜱᴀɢᴇ Oʀ Lᴀꜱᴛ Mᴇꜱꜱᴀɢᴇ Lɪɴᴋ Oꜰ SᴏᴜRᴄᴇ Cʜᴀᴛ.\n/cancel - Tᴏ Cᴀɴᴄᴇʟ Tʜɪꜱ Pʀᴏᴄᴇꜱꜱ"
  TO_MSG = "<b><u>Cʜᴏᴏꜱᴇ TᴀRɢᴇᴛ Cʜᴀᴛ</u></b>\n\nCʜᴏᴏꜱᴇ YᴏᴜR TᴀRɢᴇᴛ Cʜᴀᴛ Fʀᴏᴍ Tʜᴇ Gɪᴠᴇᴇɴ Bᴜᴛᴛᴏɴꜱ.\n/cancel - Tᴏ Cᴀɴᴄᴇʟ Tʜɪꜱ Pʀᴏᴄᴇꜱꜱ"
  RANGE_MSG = """<b><u>Sᴇᴛ FᴏRᴡᴀRDɪɴɢ Rᴀɴɢᴇ</u></b>

Tʜᴇ ʙᴏᴛ ᴡɪʟʟ ғᴏʀᴡᴀʀᴅ ᴍᴇꜱꜱᴀɢᴇꜱ ᴡɪᴛʜɪɴ ᴛʜᴇ ꜱᴩᴇᴄɪꜰɪᴇᴅ ᴍᴇꜱꜱᴀɢᴇ ID ʀᴀɴɢᴇ.

Iꜰ ʏᴏᴜ Dᴏ ɴᴏᴛ ᴄʜᴀɴɢᴇ ᴛʜᴇ IDs, Tʜᴇ ʙᴏᴛ ᴡɪʟʟ FᴏRᴡᴀRᴅ Tʜᴇ ᴇɴᴛɪRᴇ ᴄʜᴀᴛ ʜɪꜱᴛᴏRʏ.
"""
  CANCEL = "<b> Pʀᴏᴄᴇꜱꜱ Cᴀɴᴄᴇʟʟᴇᴅ Sᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ! </b>"
  BOT_DETAILS = "<b><u>📄 Bᴏᴛ Dᴇᴛᴀɪʟꜱ</u></b>\n\n<b>➣ Nᴀᴍᴇ :</b> <code>{}</code>\n<b>➣ Bᴏᴛ ID :</b> <code>{}</code>\n<b>➣ UꜱᴇRɴᴀᴍᴇ :</b> @{}"
  USER_DETAILS = "<b><u>📄 UꜱᴇRʙᴏᴛ Dᴇᴛᴀɪʟꜱ</u></b>\n\n<b>➣ Nᴀᴍᴇ :</b> <code>{}</code>\n<b>➣ UꜱᴇR ID :</b> <code>{}</code>\n<b>➣ UꜱᴇRɴᴀᴍᴇ :</b> @{}"
         
  TEXT = """<b><u>FᴏRᴡᴀRD Sᴛᴀᴛᴜꜱ</u></b>
  
<b>🕵 Fᴇᴛᴄʜᴇᴅ Mᴇꜱꜱᴀɢᴇ :</b> <code>{}</code>
<b>✅ Sᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ FᴏRᴡᴀRD :</b> <code>{}</code>
<b>👥 Dᴜʙʟɪᴄᴀᴛᴇ Mᴇꜱꜱᴀɢᴇ :</b> <code>{}</code>
<b>🗑 Dᴇʟᴇᴛᴇᴅ Mᴇꜱꜱᴀɢᴇ :</b> <code>{}</code>
<b>🪆 Sᴋɪᴩᴩᴇᴅ Mᴇꜱꜱᴀɢᴇ :</b> <code>{}</code>
<b>🔁 FɪʟᴛᴇRᴇᴅ Mᴇꜱꜱᴀɢᴇ :</b> <code>{}</code>
<b>📊 CᴜRʀᴇɴᴛ Sᴛᴀᴛᴜꜱ :</b> <code>{}</code>
<b>🔥 PᴇRᴄᴇɴᴛᴀɢᴇ :</b> <code>{}</code> %

{}
"""

  TEXT1 = """<b><u>FᴏRᴡᴀRD Sᴛᴀᴛᴜꜱ</u></b>

<b>🕵 Fᴇᴛᴄʜᴇᴅ Mᴇꜱꜱᴀɢᴇ :</b> <code>{}</code>
<b>✅ Sᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ FᴏRᴡᴀRD :</b> <code>{}</code>
<b>👥 Dᴜʙʟɪᴄᴀᴛᴇ Mᴇꜱꜱᴀɢᴇ :</b> <code>{}</code>
<b>🗑 Dᴇʟᴇᴛᴇᴅ Mᴇꜱꜱᴀɢᴇ :</b> <code>{}</code>
<b>🪆 Sᴋɪᴩᴩᴇᴅ Mᴇꜱꜱᴀɢᴇ :</b> <code>{}</code>
<b>📊 Sᴛᴀᴛꜱ :</b> <code>{}</code>
<b>⏳ PʀᴏɢRᴇꜱꜱ :</b> <code>{}</code>
<b>⏰ Eᴛᴀ :</b> <code>{}</code>
{}"""

  DUPLICATE_TEXT = """<b><u>UɴᴇQᴜɪꜰʏ Sᴛᴀᴛᴜꜱ</u></b>

<b>🕵 Fᴇᴛᴄʜᴇᴅ Fɪʟᴇꜱ :</b> <code>{}</code>

<b>👥 Dᴜʙʟɪᴄᴀᴛᴇ Dᴇʟᴇᴛᴇᴅ :</b> <code>{}</code>

{}
"""
  DOUBLE_CHECK_RANGE = """<b><u>Dᴏᴜʙʟᴇ Cʜᴇᴄᴋɪɴɢ</u></b>
  
BᴇꜰᴏRᴇ FᴏRᴡᴀRDɪɴɢ Tʜᴇ Mᴇꜱꜱᴀɢᴇꜱ Cʟɪᴄᴋ Tʜᴇ Yᴇꜱ Bᴜᴛᴛᴏɴ Oɴʟʏ AꜰᴛᴇR Cʜᴇᴄᴋɪɴɢ Tʜᴇ Fᴏʟʟᴏᴡɪɴɢ

<b>★ YᴏᴜR Bᴏᴛ :</b> [{botname}](t.me/{botuname})
<b>★ Fʀᴏᴍ Cʜᴀɴɴᴇʟ :</b> <code>{from_chat}</code>
<b>★ Tᴏ Cʜᴀɴɴᴇʟ :</b> <code>{to_chat}</code>
<b>★ Mᴇꜱꜱᴀɢᴇ Rᴀɴɢᴇ :</b> <code>{start_id} to {end_id}</code>

<i>° [{botname}](t.me/{botuname}) Mᴜꜱᴛ Bᴇ Aᴅᴍɪɴ Iɴ <b>TᴀRɢᴇᴛ Cʜᴀᴛ</b></i> (<code>{to_chat}</code>)
<i>° Iꜰ Tʜᴇ <b>SᴏᴜRᴄᴇ Cʜᴀᴛ</b> Iꜱ Pʀɪᴠᴀᴛᴇ YᴏᴜR UsᴇRʙᴏᴛ Mᴜꜱᴛ Bᴇ MᴇᴍʙᴇR Oʀ YᴏᴜR Bᴏᴛ Mᴜꜱᴛ Bᴇ Aᴅᴍɪɴ Iɴ TʜᴇRᴇ Aʟꜱᴏ</i>

<b>Iꜰ Tʜᴇ Aʙᴏᴠᴇ Iꜱ CʜᴇᴄᴋᴇD Tʜᴇɴ Tʜᴇ Yᴇꜱ Bᴜᴛᴛᴏɴ Cᴀɴ Bᴇ CʟɪᴄᴋᴇD</b>"""

  FORWARDELAY_TXT = """<b><u>Sᴇᴛ FᴏRᴡᴀRDɪɴɢ Dᴇʟᴀʏ</u></b>

Usᴇ Tʜɪs ᴄᴏᴍᴍᴀɴᴅ Tᴏ Sᴇᴛ ᴀ ᴄᴜsᴛᴏᴍ Dᴇʟᴀʏ (ɪɴ Sᴇᴄᴏɴᴅs) ʙᴇᴛᴡᴇᴇɴ FᴏRᴡᴀRDᴇᴅ Mᴇꜱꜱᴀɢᴇꜱ ᴛᴏ ᴀᴠᴏɪᴅ TᴇʟᴇɢRᴀᴍ's Fʟᴏᴏᴅ ʟɪᴍɪᴛs.

<b>Usᴀɢᴇ:</b> <code>/FᴏRᴡᴀRᴅᴇʟᴀʏ [Dᴇʟᴀʏ_ɪɴ_Sᴇᴄᴏɴᴅs]</code>
<b>E.g.:</b> <code>/FᴏRᴡᴀRᴅᴇʟᴀʏ 0.5</code> (sᴇᴛs a ʜᴀʟf-sᴇᴄᴏɴᴅ Dᴇʟᴀʏ)
<b>E.g.:</b> <code>/FᴏRᴡᴀRᴅᴇʟᴀʏ 2</code> (sᴇᴛs a ᴛᴡᴏ-sᴇᴄᴏɴᴅ Dᴇʟᴀʏ)

Tʜᴇ Dᴇfᴀᴜʟᴛ Dᴇʟᴀʏ ɪs 1 Sᴇᴄᴏɴᴅ."""

# =========================================================================
# PLUGINS
# =========================================================================

# plugins/__init__.py
routes = web.RouteTableDef()
async def web_server():
    web_app = web.Application(client_max_size=30000000)
    web_app.add_routes(routes)
    return web_app

# plugins/admin.py
botStartTime = time.time()
@Client.on_message(filters.private & filters.command(["ping", "p"]))
async def ping(_, message):
    start_t = time.time()
    rm = await message.reply_text("Pinging....", quote=True)
    end_t = time.time()
    time_taken_s = (end_t - start_t) * 1000
    await rm.edit(f"Ping 🔥!\n{time_taken_s:.3f} ms")
    return time_taken_s

@Client.on_message(filters.command(["stats", "status", "s"]) & filters.user(Config.OWNER_ID))
async def get_stats(bot, message):
    users_count, bots_count = await db.total_users_bots_count()
    total_channels = await db.total_channels()
    uptime = get_readable_time(time.time() - botStartTime)
    start_t = time.time()
    st = await message.reply('**Processing The Details.....**')
    end_t = time.time()
    time_taken_s = (end_t - start_t) * 1000
    await st.edit(text=f"**--Bot Status--** \n\n**⌚ Bot Uptime :** `{uptime}` \n**🐌 Current Ping :** `{time_taken_s:.3f} ms` \n**👭 Total Users :** `{users_count}` \n\n**🤖 Total Bots :** `{bots_count}` \n**✅ Forwarding :** `{temp.forwardings}` \n**🔥 Total Channel :** `{total_channels}` \n**🚫 Banned Users :** `{temp.BANNED_USERS}`")

@Client.on_message(filters.private & filters.command(["donate", "d"]))
async def donate(client, message):
	text = "<b>breh. this is a personal bot...</b> <code>wassup nigga</code>"
	keybord = InlineKeyboardMarkup([
        			[InlineKeyboardButton("🦋 Admin",url = "https://t.me/partDevil"),
        			InlineKeyboardButton("✖️ Close",callback_data = "close_btn") ]])
	await message.reply_text(text = text,reply_markup = keybord)

# plugins/broadcast.py
@Client.on_message(filters.command(["broadcast", "b"]) & filters.user(Config.OWNER_ID) & filters.reply)
async def broadcast (bot, message):
    users = await db.get_all_users()
    b_msg = message.reply_to_message
    sts = await message.reply_text(
        text='Broadcasting Your Messages...'
    )
    start_time = time.time()
    total_users, k = await db.total_users_bots_count()
    done = 0
    blocked = 0
    deleted = 0
    failed = 0
    success = 0
    async for user in users:
        pti, sh = await broadcast_messages(int(user['id']), b_msg, bot.log)
        if pti:
            success += 1
            await asyncio.sleep(2)
        elif pti == False:
            if sh == "Blocked":
                blocked+=1
            elif sh == "Deleted":
                deleted += 1
            elif sh == "Error":
                failed += 1
        done += 1
        if not done % 20:
            await sts.edit(f"<b><u>Broadcast In Progress :</u></b>\n\nTotal Users {total_users}\nCompleted: {done} / {total_users}\nSuccess: {success}\nBlocked: {blocked}\nDeleted: {deleted}")
    time_taken = datetime.timedelta(seconds=int(time.time()-start_time))
    await sts.edit(f"<b><u>Broadcast Completed :</u></b>\n\nCompleted in {time_taken} seconds.\n\nTotal Users {total_users}\nCompleted: {done} / {total_users}\nSuccess: {success}\nBlocked: {blocked}\nDeleted: {deleted}")

async def broadcast_messages(user_id, message, log):
    try:
        await message.copy(chat_id=user_id)
        return True, "Success"
    except FloodWait as e:
        await asyncio.sleep(e.x)
        return await broadcast_messages(user_id, message, log)
    except InputUserDeactivated:
        await db.delete_user(int(user_id))
        log.info(f"{user_id}-Removed from Database, since deleted account.")
        return False, "Deleted"
    except UserIsBlocked:
        log.info(f"{user_id} -Blocked the bot.")
        return False, "Blocked"
    except Exception as e:
        return False, "Error"

# plugins/commands.py
@Client.on_message(filters.private & filters.command(['start']))
async def start(client, message):
    user = message.from_user
    try:
        if not await db.is_user_exist(user.id):
            await db.add_user(user.id, user.first_name)
    except Exception as e:
        await message.reply(f"⚠️ An error occurred while checking or adding the user. {e}")
        logger.error(f"Error in user registration: {e}")

    reply_markup = InlineKeyboardMarkup(main_buttons)
    text=Translation.START_TXT.format(user.mention)
    await message.reply_photo(
        photo=random.choice(SYD),
        caption=text,
        reply_markup=reply_markup
    )

@Client.on_message(filters.private & filters.command(['restart', "r"]) & filters.user(Config.OWNER_ID))
async def restart(client, message):
    msg = await message.reply_text(
        text="<i>Trying To Restarting.....</i>",
        quote=True
    )
    await asyncio.sleep(5)
    await msg.edit("<i>Successfully Restarted</i>")
    os.execl(sys.executable, sys.executable, *sys.argv)

@Client.on_message(filters.command("start") & filters.chat(-1002687879857))
async def sydstart(client, message):
    await message.reply_text(".")

@Client.on_callback_query(filters.regex(r'^help'))
async def helpcb(bot, query):
    await query.message.edit_text(
        text=Translation.HELP_TXT,
        reply_markup=InlineKeyboardMarkup(
            [[
            InlineKeyboardButton('∿ Hᴏᴡ To Usᴇ Mᴇ ∿', callback_data='how_to_use')
            ],[
            InlineKeyboardButton('⛭ SᴇᴛᴛɪɴGS ⛭', callback_data='settings#main'),
            InlineKeyboardButton('∗ SᴛᴀᴛS ∗', callback_data='status')
            ],[
            InlineKeyboardButton('⇇ Bᴀᴄᴋ', callback_data='back')
            ]]
        ))

@Client.on_message(filters.private & filters.command(["forwardelay", "fd"]))
async def forward_delay(client, message):
    if len(message.command) < 2:
        return await message.reply_text(Translation.FORWARDELAY_TXT)

    try:
        delay = float(message.command[1])
        if delay < 0:
            return await message.reply_text("The delay must be a positive number.")

        user_id = message.from_user.id
        await update_configs(user_id, 'forward_delay', delay)
        await message.reply_text(f"Forwarding delay set to {delay} seconds.")
    except ValueError:
        await message.reply_text("Invalid input. Please provide a number.")

@Client.on_callback_query(filters.regex(r'^how_to_use'))
async def how_to_use(bot, query):
    await query.message.edit_text(
        text=Translation.HOW_USE_TXT,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('⇇ Bᴀᴄᴋ', callback_data='help')]]),
        disable_web_page_preview=True
    )

@Client.on_callback_query(filters.regex(r'^back'))
async def back(bot, query):
    reply_markup = InlineKeyboardMarkup(main_buttons)
    await query.message.edit_text(
       reply_markup=reply_markup,
       text=Translation.START_TXT.format(
                query.from_user.first_name))

@Client.on_callback_query(filters.regex(r'^about'))
async def about(bot, query):
    await query.message.edit_text(
        text=Translation.ABOUT_TXT.format(bot.me.mention),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('⇇ Bᴀᴄᴋ', callback_data='back')]]),
        disable_web_page_preview=True,
        parse_mode=enums.ParseMode.HTML,
    )

@Client.on_callback_query(filters.regex(r'^status'))
async def status(bot, query):
    users_count, bots_count = await db.total_users_bots_count()
    total_channels = await db.total_channels()
    await query.message.edit_text(
        text=Translation.STATUS_TXT.format(users_count, bots_count, temp.forwardings, total_channels, temp.BANNED_USERS ),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('⇇ Bᴀᴄᴋ', callback_data='help')]]),
        parse_mode=enums.ParseMode.HTML,
        disable_web_page_preview=True,
    )

# plugins/public.py
SYD_CHANNELS = ["norFederation"]
@Client.on_message(filters.private & filters.command(["fwd", "forward"]))
async def run(bot, message):
    buttons = []
    user_id = message.from_user.id
    bots = await db.get_all_bots(user_id)
    if not bots:
        return await message.reply("Yᴏᴜ Dɪᴅ Nᴏᴛ Aᴅᴅᴇᴅ Aɴʏ Bᴏᴛ. Pʟᴇᴀꜱᴇ Aᴅᴅ A Bᴏᴛ Usɪɴɢ /settings !")
    channels = await db.get_user_channels(user_id)
    if not channels:
       return await message.reply_text("Please Set A To Channel In /settings Before Forwarding")
    for _bot in bots:
        text = f"🤖 {_bot['name']}" if _bot['is_bot'] else f"👤 {_bot['name']}"
        buttons.append([InlineKeyboardButton(text, callback_data=f"fwd_bot_{_bot['id']}")])
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="close_btn")])
    await message.reply_text("<b><u>Cʜᴏᴏꜱᴇ Bᴏᴛ</u></b>\n\nCʜᴏᴏꜱᴇ Tʜᴇ Bᴏᴛ Yᴏᴜ Wᴀɴᴛ Tᴏ Usᴇ FᴏR FᴏRᴡᴀRDɪɴɢ.", reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex(r'^fwd_bot_'))
async def choose_target_chat(bot, query):
    await query.answer()
    user_id = query.from_user.id
    bot_id = int(query.data.split('_')[2])
    channels = await db.get_user_channels(user_id)
    if len(channels) > 0:
        unique_channels = []
        seen_ids = set()
        for channel in channels:
            if channel['chat_id'] not in seen_ids:
                unique_channels.append(channel)
                seen_ids.add(channel['chat_id'])
        buttons = []
        for channel in unique_channels:
            buttons.append([InlineKeyboardButton(f"{channel['title']}", callback_data=f"fwd_target_{bot_id}_{channel['chat_id']}")])
        buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="close_btn")])
        await query.message.edit_text("<b><u>Cʜᴏᴏꜱᴇ TᴀRɢᴇᴛ Cʜᴀᴛ</u></b>\n\nCʜᴏᴏꜱᴇ YᴏᴜR TᴀRɢᴇᴛ Cʜᴀᴛ Fʀᴏᴍ Tʜᴇ GɪᴠᴇN Bᴜᴛᴛᴏɴꜱ.", reply_markup=InlineKeyboardMarkup(buttons))
    else:
       await query.message.edit_text("Please Set A To Channel In /settings Before Forwarding")

@Client.on_callback_query(filters.regex(r'^fwd_target_'))
async def get_source_chat(bot, query):
    await query.answer()
    user_id = query.from_user.id
    bot_id, toid = query.data.split('_')[2:]
    toid = int(toid)
    bot_id = int(bot_id)
    _bot = await db.get_bot(user_id, bot_id)
    channels = await db.get_user_channels(user_id)
    to_title = next((c['title'] for c in channels if c['chat_id'] == toid), 'Unknown')
    await query.message.delete()
    try:
        fromid_msg = await bot.ask(query.message.chat.id, Translation.FROM_MSG, timeout=300)
    except asyncio.exceptions.TimeoutError:
        return await bot.send_message(query.message.chat.id, Translation.CANCEL)
    if fromid_msg.text and fromid_msg.text.startswith('/'):
        return await fromid_msg.reply(Translation.CANCEL)
    if fromid_msg.text and not fromid_msg.forward_date:
        regex = re.compile(r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$")
        match = regex.match(fromid_msg.text.replace("?single", ""))
        if not match:
            return await fromid_msg.reply('Invalid Link')
        chat_id = match.group(4)
        if chat_id.isnumeric():
            chat_id  = int(("-100" + chat_id))
    elif fromid_msg.forward_from_chat and fromid_msg.forward_from_chat.type in [enums.ChatType.CHANNEL]:
        chat_id = fromid_msg.forward_from_chat.username or fromid_msg.forward_from_chat.id
    else:
        await fromid_msg.reply_text("Invalid!")
        return
    try:
        title = (await bot.get_chat(chat_id)).title
        oldest_msg = await bot.get_chat_history(chat_id, limit=1, offset=-1)
        newest_msg = await bot.get_chat_history(chat_id, limit=1)
        start_id = oldest_msg[0].id if oldest_msg else 1
        end_id = newest_msg[0].id if newest_msg else 1
    except (PrivateChat, ChannelPrivate, ChannelInvalid):
        title = "private" if fromid_msg.text else fromid_msg.forward_from_chat.title
        start_id = 1
        end_id = fromid_msg.forward_from_message_id
    except (UsernameInvalid, UsernameNotModified):
        return await fromid_msg.reply('Invalid Link Specified.')
    except Exception as e:
        return await fromid_msg.reply(f'Errors - {e}')
    await bot.send_message(
        chat_id=query.message.chat.id,
        text=Translation.RANGE_MSG,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton('Range: {} to {}'.format(start_id, end_id), callback_data='dummy_button'),
        ],[
            InlineKeyboardButton('Set Start ID', callback_data=f'set_id_start_{start_id}_{user_id}_{bot_id}_{toid}_{chat_id}_{end_id}'),
            InlineKeyboardButton('Set End ID', callback_data=f'set_id_end_{end_id}_{user_id}_{bot_id}_{toid}_{chat_id}_{start_id}')
        ],[
            InlineKeyboardButton('✅ Start Forwarding', callback_data=f'start_forwarding_{user_id}_{bot_id}_{chat_id}_{toid}_{start_id}_{end_id}'),
        ]])
    )

@Client.on_callback_query(filters.regex(r'^set_id_'))
async def set_message_id(bot, query):
    await query.answer()
    action, id_type, current_id_str, user_id, bot_id, toid, fromid, other_id = query.data.split('_', 7)
    user_id, bot_id, toid, fromid, other_id = int(user_id), int(bot_id), int(toid), int(fromid), int(other_id)
    prompt = f"Please enter the new {'Start' if id_type == 'start' else 'End'} Message ID."
    cancel_button = InlineKeyboardMarkup([[InlineKeyboardButton('❌ Cancel', callback_data='close_btn')]])
    ask_msg = await bot.send_message(
        chat_id=query.message.chat.id,
        text=prompt,
        reply_markup=cancel_button
    )
    try:
        new_id_msg = await bot.listen(filters.private & filters.user(user_id), chat_id=user_id, timeout=300)
        new_id = int(new_id_msg.text)
        await ask_msg.delete()
        await new_id_msg.delete()
        start_id = new_id if id_type == 'start' else other_id
        end_id = new_id if id_type == 'end' else other_id
        if start_id > end_id:
            return await bot.send_message(query.message.chat.id, "The start ID cannot be greater than the end ID.")
        range_button = InlineKeyboardButton('Range: {} to {}'.format(start_id, end_id), callback_data='dummy_button')
        set_start_button = InlineKeyboardButton('Set Start ID', callback_data=f'set_id_start_{start_id}_{user_id}_{bot_id}_{toid}_{fromid}_{end_id}')
        set_end_button = InlineKeyboardButton('Set End ID', callback_data=f'set_id_end_{end_id}_{user_id}_{bot_id}_{toid}_{fromid}_{start_id}')
        new_buttons = [[range_button], [set_start_button, set_end_button], [InlineKeyboardButton('✅ Start Forwarding', callback_data=f'start_forwarding_{user_id}_{bot_id}_{fromid}_{toid}_{start_id}_{end_id}')]]
        await query.message.edit_text(
            text=query.message.text,
            reply_markup=InlineKeyboardMarkup(new_buttons)
        )
    except asyncio.exceptions.TimeoutError:
        await bot.send_message(query.message.chat.id, "Process timed out.")
    except ValueError:
        await bot.send_message(query.message.chat.id, "Invalid ID. Please enter a number.")

@Client.on_callback_query(filters.regex(r'^start_forwarding_'))
async def handle_start_button(bot, query):
    await query.answer()
    _, _, user_id, bot_id, fromid, toid, start_id, end_id = query.data.split('_')
    forward_id = f"{query.from_user.id}-{query.id}"
    buttons = [[
        InlineKeyboardButton('Yᴇꜱ', callback_data=f"start_public_{forward_id}_{bot_id}_{fromid}_{toid}_{start_id}_{end_id}"),
        InlineKeyboardButton('Nᴏ', callback_data="close_btn")
    ]]
    await query.message.delete()
    _bot = await db.get_bot(query.from_user.id, int(bot_id))
    channels = await db.get_user_channels(query.from_user.id)
    to_title = next((c['title'] for c in channels if c['chat_id'] == int(toid)), 'Unknown')
    try:
        from_title = (await bot.get_chat(int(fromid))).title
    except Exception:
        from_title = "private"
    await bot.send_message(
        chat_id=query.message.chat.id,
        text=Translation.DOUBLE_CHECK_RANGE.format(botname=_bot['name'], botuname=_bot['username'], from_chat=from_title, to_chat=to_title, start_id=start_id, end_id=end_id),
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    STS(forward_id, int(bot_id)).store(int(fromid), int(toid), int(start_id), int(end_id), int(bot_id))

@Client.on_callback_query(filters.regex("check_subscription"))
async def check_subscription(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    not_joined_channels = []
    for channel in SYD_CHANNELS:
        try:
            user = await client.get_chat_member(channel, user_id)
            if user.status in {"kicked", "left"}:
                not_joined_channels.append(channel)
        except UserNotParticipant:
            not_joined_channels.append(channel)
    if not not_joined_channels:
        await callback_query.message.edit_text(
            "**Tʜᴀɴᴋꜱ ✨, Yᴏᴜ ʜᴀᴠᴇ ᴊᴏɪɴᴇᴅ ᴏɴ ᴀʟʟ ᴛʜᴇ ʀᴇqᴜɪʀᴇᴅ ᴄʜᴀɴɴᴇʟꜱ. \nCʟɪᴄᴋ ᴏɴ 😊 😂 /forward ɴᴏᴡ ᴛᴏ ꜱᴛᴀʀᴛ ᴛʜᴇ ᴩʀᴏᴄᴇꜱꜱ.....⚡**"
        )
        await callback_query.message.reply("🎊")
    else:
        buttons = [
            [
                InlineKeyboardButton(
                    text=f"✧ Jᴏɪɴ {channel.capitalize().replace('_', ' ')} ✧",
                    url=f"https://t.me/{channel}",
                )
            ]
            for channel in not_joined_channels
        ]
        buttons.append(
            [
                InlineKeyboardButton(
                    text="✧ Jᴏɪɴ Bᴀᴄᴋ Uᴩ ✧", url="https://t.me/+bAsrcnckBNdkMjVi"
                )
            ]
        )
        buttons.append(
            [
                InlineKeyboardButton(
                    text="☑ ᴊᴏɪɴᴇᴅ ☑", callback_data="check_subscription"
                )
            ]
        )
        text = "**Sᴛɪʟʟ 🥲, ʏᴏᴜ ʜᴀᴠᴇɴᴛ ᴊᴏɪɴᴇᴅ ɪɴ ᴏᴜʀ ᴀʟʟ ʀᴇqᴜɪʀᴇᴅ ᴄʜᴀɴɴᴇʟꜱ, ᴩʟᴇᴀꜱᴇ ᴅᴏ ꜱᴏ ᴛᴏ ᴄᴏɴᴛɪɴᴜᴇ..✨ .**"
        await callback_query.message.edit_text(
            text=text, reply_markup=InlineKeyboardMarkup(buttons)
     )

# plugins/regix.py
@Client.on_callback_query(filters.regex(r'^start_public_'))
async def pub_(bot, message):
    user = message.from_user.id
    temp.CANCEL[user] = False
    data_parts = message.data.split('_')
    forward_id, bot_id, fromid, toid, start_id, end_id = data_parts[2], int(data_parts[3]), int(data_parts[4]), int(data_parts[5]), int(data_parts[6]), int(data_parts[7])
    if temp.lock.get(user) and str(temp.lock.get(user))=="True":
      return await message.answer("Pʟᴇᴀꜱᴇ Wᴀɪᴛ Uɴᴛɪʟ Pʀᴇᴠɪᴏᴜꜱ Tᴀꜱᴋ Cᴏᴍᴩʟᴇᴛᴇ !", show_alert=True)
    sts = STS(forward_id, bot_id)
    if not sts.verify():
      await message.answer("Re-initializing task...", show_alert=True)
      sts.store(fromid, toid, start_id, end_id, bot_id)
      i = sts.get(full=True)
    else:
      i = sts.get(full=True)
    if i.TO in temp.IS_FRWD_CHAT:
      return await message.answer("In Target Chat A Task Is Progressing. Please Wait Until Task Complete", show_alert=True)
    m = await msg_edit(message.message, "Verifying Your Data's, Please Wait.")
    _bot = await db.get_bot(user, bot_id)
    if not _bot:
      return await msg_edit(m, "You Didn't Added Any Bot. Please Add A Bot Usɪɴɢ /settings !", wait=True)
    configs = await db.get_configs(user)
    caption = configs.get('caption')
    forward_tag = configs.get('forward_tag')
    protect = configs.get('protect')
    button = configs.get('button')
    try:
      client = await start_clone_bot(CLIENT.client(_bot))
    except Exception as e:
      return await m.edit(f'Failed to start client: {e}')
    await msg_edit(m, "Processing...")
    try:
       chat = await client.get_chat(fromid)
       if chat.type == ChatType.PRIVATE:
           try:
              await client.join_chat(fromid)
           except UserNotParticipant:
               return await msg_edit(m, f"Source Chat Is A Private Channel / Group. Please make your userbot a member or your bot an admin there.", wait=True)
    except (PrivateChat, ChannelPrivate, ChannelInvalid, PeerIdInvalid) as e:
       await stop(client, user)
       return await msg_edit(m, f"Source chat may be private or invalid. Error: {e}", retry_btn(forward_id), True)
    except ChatAdminRequired:
       await stop(client, user)
       return await msg_edit(m, f"Please Make Your Bot Admin In Source Channel With Full Permissions", retry_btn(forward_id), True)
    try:
       k = await client.send_message(toid, "Tᴇꜱᴛɪɴɢ......")
       await k.delete()
    except Exception as e:
       await stop(client, user)
       return await msg_edit(m, f"Please Make Your Bot Admin In Target Channel With Full Permissions. Error: {e}", retry_btn(forward_id), True)
    temp.forwardings += 1
    await db.add_frwd(user)
    await send(client, user, "FᴏRᴡᴀRDɪɴɢ SᴛᴀRᴛᴇᴅ 🗝️")
    sts.add(time=True)
    forward_delay = configs.get('forward_delay', 1.0)
    await msg_edit(m, "Pʀᴏᴄᴄᴇꜱꜱɪɴɢ...")
    temp.IS_FRWD_CHAT.append(toid)
    temp.lock[user] = locked = True
    if locked:
        try:
          MSG = []
          pling = 0
          total_messages = end_id - start_id + 1
          sts.data[forward_id]['total'] = total_messages
          await edit(m, 'PʀᴏɢRᴇꜱꜱꜱɪɴɢ', 10, sts)
          message_ids_to_fetch = list(range(start_id, end_id + 1))
          batch_size = 100
          for i in range(0, len(message_ids_to_fetch), batch_size):
              batch_ids = message_ids_to_fetch[i:i + batch_size]
              messages_to_process = await client.get_messages(chat_id=fromid, message_ids=batch_ids)
              messages_to_process.sort(key=lambda msg: msg.id)
              for message in messages_to_process:
                if await is_cancelled(client, user, m, sts):
                   return
                if pling % 20 == 0:
                   await edit(m, 'PʀᴏɢRᴇꜱꜱɪɴɢ', 10, sts)
                pling += 1
                sts.add('fetched')
                if message == "DUPLICATE":
                   sts.add('duplicate')
                   continue
                elif message == "FILTERED":
                   sts.add('filtered')
                   continue
                if message.empty or message.service:
                   sts.add('deleted')
                   continue
                if forward_tag:
                   MSG.append(message.id)
                   notcompleted = len(MSG)
                   completed = sts.get('total') - sts.get('fetched')
                   if (notcompleted >= 100 or completed <= 100):
                      await forward(client, MSG, m, sts, protect)
                      sts.add('total_files', notcompleted)
                      await asyncio.sleep(forward_delay)
                      MSG = []
                else:
                   new_caption = custom_caption(message, caption)
                   details = {"msg_id": message.id, "media": media(message), "caption": new_caption, 'button': button, "protect": protect}
                   await copy(client, details, m, sts)
                   sts.add('total_files')
                   await asyncio.sleep(forward_delay)
        except Exception as e:
            await msg_edit(m, f'<b>Error :</b>\n<code>{e}</code>', wait=True)
            temp.IS_FRWD_CHAT.remove(toid)
            return await stop(client, user)
        temp.IS_FRWD_CHAT.remove(toid)
        await send(client, user, "FᴏRᴡᴀRDɪɴɢ Cᴏᴍᴩʟᴇᴛᴇᴅ 😇")
        await edit(m, 'Completed', "completed", sts)
        await stop(client, user)

async def copy(bot, msg, m, sts):
   try:
     if msg.get("media") and msg.get("caption"):
        await bot.send_cached_media(
              chat_id=sts.get('TO'),
              file_id=msg.get("media"),
              caption=msg.get("caption"),
              reply_markup=msg.get('button'),
              protect_content=msg.get("protect"))
     else:
        await bot.copy_message(
              chat_id=sts.get('TO'),
              from_chat_id=sts.get('FROM'),
              caption=msg.get("caption"),
              message_id=msg.get("msg_id"),
              reply_markup=msg.get('button'),
              protect_content=msg.get("protect"))
   except FloodWait as e:
     await edit(m, 'PʀᴏɢRᴇꜱꜱɪɴɢ', e.value, sts)
     await asyncio.sleep(e.value)
     await edit(m, 'PʀᴏɢRᴇꜱꜱɪɴɢ', 10, sts)
     await copy(bot, msg, m, sts)
   except Exception as e:
     print(e)
     sts.add('deleted')

async def forward(bot, msg, m, sts, protect):
   try:
     await bot.forward_messages(
           chat_id=sts.get('TO'),
           from_chat_id=sts.get('FROM'),
           protect_content=protect,
           message_ids=msg)
   except FloodWait as e:
     await edit(m, 'PʀᴏɢRᴇꜱꜱɪɴɢ', e.value, sts)
     await asyncio.sleep(e.value)
     await edit(m, 'PʀᴏɢRᴇꜱꜱɪɴɢ', 10, sts)
     await forward(bot, msg, m, sts, protect)

PROGRESS = """
📈 PᴇRᴄᴇɴᴛᴀɢᴇ : {0} %
♻️ Fᴇᴛᴄʜᴇᴅ : {1}
🔥 FᴏRᴡᴀRᴅᴇᴅ : {2}
🫠 Rᴇᴍᴀɪɴɪɴɢ : {3}
📊 Sᴛᴀᴛᴜꜱ : {4}
⏳️ Eᴛᴀ : {5}
"""

async def msg_edit(msg, text, button=None, wait=None):
    try:
        return await msg.edit(text, reply_markup=button, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    except MessageNotModified:
        pass
    except FloodWait as e:
        if wait:
           await asyncio.sleep(e.value)
           return await msg_edit(msg, text, button, wait)

async def edit(msg, title, status, sts):
   i = sts.get(full=True)
   status = 'FᴏRᴡᴀRDɪɴɢ' if status == 10 else f"Sʟᴇᴇᴩɪɴɢ {status} s" if str(status).isnumeric() else status
   percentage = "{:.0f}".format(float(i.fetched)*100/float(i.total))
   now = time.time()
   diff = int(now - i.start)
   speed = sts.divide(i.fetched, diff)
   elapsed_time = round(diff) * 1000
   time_to_completion = round(sts.divide(i.total - i.fetched, int(speed))) * 1000
   estimated_total_time = elapsed_time + time_to_completion
   progress = "▰{0}{1}".format(
       ''.join(["▰" for i in range(math.floor(int(percentage) / 10))]),
       ''.join(["▱" for i in range(10 - math.floor(int(percentage) / 10))]))
   button =  [[InlineKeyboardButton(title, f'fwrdstatus#{status}#{estimated_total_time}#{percentage}#{i.id}')]]
   estimated_total_time = TimeFormatter(milliseconds=estimated_total_time)
   estimated_total_time = estimated_total_time if estimated_total_time != '' else '0 s'
   text = TEXT.format(i.fetched, i.total_files, i.duplicate, i.deleted, i.skip, status, percentage, estimated_total_time, progress)
   if status in ["cancelled", "completed"]:
      button.append(
         [InlineKeyboardButton('Channel', url='https://t.me/norFederation'),
         InlineKeyboardButton('Me', url='https://t.me/partDevil')]
         )
   else:
      button.append([InlineKeyboardButton('✖️ Cᴀɴᴄᴇʟ ✖️', 'terminate_frwd')])
   await msg_edit(msg, text, InlineKeyboardMarkup(button))

async def is_cancelled(client, user, msg, sts):
   if temp.CANCEL.get(user)==True:
      temp.IS_FRWD_CHAT.remove(sts.TO)
      await edit(msg, "Cancelled", "completed", sts)
      await send(client, user, "❌ FᴏRᴡᴀRᴅɪɴɢ Pʀᴏᴄᴇꜱꜱ Cᴀɴᴄᴇʟʟᴇᴅ")
      await stop(client, user)
      return True
   return False

async def stop(client, user):
   try:
     await client.stop()
   except:
     pass
   await db.rmve_frwd(user)
   temp.fᴏRᴡᴀRDɪɴɢꜱ -= 1
   temp.lock[user] = False

async def send(bot, user, text):
   try:
      await bot.send_message(user, text=text)
   except:
      pass

def custom_caption(msg, caption):
  if msg.media:
    if (msg.video or msg.document or msg.audio or msg.photo):
      media = getattr(msg, msg.media.value, None)
      if media:
        file_name = getattr(media, 'file_name', '')
        file_size = getattr(media, 'file_size', '')
        fcaption = getattr(msg, 'caption', '')
        if fcaption:
          fcaption = fcaption.html
        if caption:
          return caption.format(filename=file_name, size=get_size(file_size), caption=fcaption)
        return fcaption
  return None

def get_size(size):
  units = ["Bytes", "KB", "MB", "GB", "TB", "PB", "EB"]
  size = float(size)
  i = 0
  while size >= 1024.0 and i < len(units):
     i += 1
     size /= 1024.0
  return "%.2f %s" % (size, units[i])

def media(msg):
  if msg.media:
     media = getattr(msg, msg.media.value, None)
     if media:
        return getattr(media, 'file_id', None)
  return None

def TimeFormatter(milliseconds: int) -> str:
    seconds, milliseconds = divmod(int(milliseconds), 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    tmp = ((str(days) + "d, ") if days else "") + \
        ((str(hours) + "h, ") if hours else "") + \
        ((str(minutes) + "m, ") if minutes else "") + \
        ((str(seconds) + "s, ") if seconds else "") + \
        ((str(milliseconds) + "ms, ") if milliseconds else "")
    return tmp[:-2]

def retry_btn(id):
    return InlineKeyboardMarkup([[InlineKeyboardButton('♻️ Rᴇᴛʀʏ ♻️', f"start_public_{id}")]])

@Client.on_callback_query(filters.regex(r'^terminate_frwd$'))
async def terminate_frwding(bot, m):
    user_id = m.from_user.id
    temp.lock[user_id] = False
    temp.CANCEL[user_id] = True
    await m.answer("FᴏRᴡᴀRᴅɪɴɢ Cᴀɴᴄᴇʟʟᴇᴅ !", show_alert=True)

@Client.on_callback_query(filters.regex(r'^fwrdstatus'))
async def status_msg(bot, msg):
    _, status, est_time, percentage, frwd_id = msg.data.split("#")
    sts = STS(frwd_id)
    if not sts.verify():
       fetched, forwarded = 0, 0
    else:
       fetched, forwarded = sts.get('fetched'), sts.get('total_files')
    remaining = fetched - forwarded
    est_time = TimeFormatter(milliseconds=int(est_time))
    est_time = est_time if (est_time != '' or status not in ['completed', 'cancelled']) else '0 s'
    return await msg.answer(PROGRESS.format(percentage, fetched, forwarded, remaining, status, est_time), show_alert=True)

@Client.on_callback_query(filters.regex(r'^close_btn$'))
async def close(bot, update):
    await update.answer()
    await update.message.delete()
    if update.message.reply_to_message:
      await update.message.reply_to_message.delete()

# plugins/route.py
@routes.get("/", allow_head=True)
async def root_route_handler(request):
    return web.json_response("filesforwardingbot : by bot cracker")

# plugins/settings.py
@Client.on_message(filters.private & filters.command(['settings']))
async def settings(client, message):
    text="<b>Cʜᴀɴɢᴇ YᴏᴜR Sᴇᴛᴛɪɴɢꜱ Aꜱ PᴇR YᴏᴜR Nᴇᴇᴅꜱ! ❄️</b>"
    await message.reply_text(
        text=text,
        reply_markup=main_buttons(),
        quote=True
    )

@Client.on_callback_query(filters.regex(r'^settings'))
async def settings_query(bot, query):
  user_id = query.from_user.id
  i, type = query.data.split("#")
  buttons = [[InlineKeyboardButton('⇇ Bᴀᴄᴋ', callback_data="settings#main")]]

  if type=="main":
     await query.message.edit_text(
       "<b>Cʜᴀɴɢᴇ YᴏᴜR Sᴇᴛᴛɪɴɢꜱ Aꜱ PᴇR YᴏᴜR Nᴇᴇᴅꜱ! ❄️</b>",
       reply_markup=main_buttons())
  elif type=="bots":
     buttons = []
     bots = await db.get_all_bots(user_id)
     if bots:
        for _bot in bots:
            text = f"🤖 {_bot['name']}" if _bot['is_bot'] else f"👤 {_bot['name']}"
            buttons.append([InlineKeyboardButton(text, callback_data=f"settings#editbot_{_bot['id']}")])
     buttons.append([InlineKeyboardButton('⨁ Aᴅᴅ Bᴏᴛ ⨁',
                      callback_data="settings#addbot")])
     buttons.append([InlineKeyboardButton('⨁ Aᴅᴅ UsᴇR Bᴏᴛ ⨁',
                      callback_data="settings#adduserbot")])
     buttons.append([InlineKeyboardButton('⇇ Bᴀᴄᴋ',
                      callback_data="settings#main")])
     await query.message.edit_text(
       "<b><u>Mʏ Bᴏᴛꜱ</u></b>\n\nYᴏᴜ Cᴀɴ Mᴀɴᴀɢᴇ YᴏᴜR Bᴏᴛꜱ Iɴ HᴇRᴇ \nAᴅᴅ Tʜɪꜱ Bᴏᴛ TᴀRɢᴇᴛ Cʜᴀᴛ ᴀɴᴅ SᴏᴜRᴄᴇ Cʜᴀᴛ ✨",
       reply_markup=InlineKeyboardMarkup(buttons))
  elif type=="addbot":
     await query.message.delete()
     bot = await CLIENT.add_bot(bot, query)
     if bot != True: return
     await query.message.reply_text(
        "<b>Bᴏᴛ Tᴏᴋᴇɴ Sᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ Aᴅᴅᴇᴅ Tᴏ Dᴀᴛᴀʙᴀꜱᴇ ✓</b>",
        reply_markup=InlineKeyboardMarkup(buttons))
  elif type=="adduserbot":
     await query.message.delete()
     user = await CLIENT.add_session(bot, query)
     if user != True: return
     await query.message.reply_text(
        "<b>Sᴇꜱꜱɪᴏɴ Sᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ Aᴅᴅᴇᴅ Tᴏ Dᴀᴛᴀʙᴀꜱᴇ ✓</b>",
        reply_markup=InlineKeyboardMarkup(buttons))
  elif type=="channels":
     buttons = []
     channels = await db.get_user_channels(user_id)
     for channel in channels:
        buttons.append([InlineKeyboardButton(f"⁕ {channel['title']}",
                         callback_data=f"settings#editchannels_{channel['chat_id']}")])
     buttons.append([InlineKeyboardButton('⨁ Aᴅᴅ Cʜᴀɴɴᴇʟ ⨁',
                      callback_data="settings#addchannel")])
     buttons.append([InlineKeyboardButton('⇇ Bᴀᴄᴋ',
                      callback_data="settings#main")])
     await query.message.edit_text(
       "<b><u>Mʏ Cʜᴀɴɴᴇʟꜱ</u></b>\n\nYᴏᴜ Cᴀɴ Mᴀɴᴀɢᴇ YᴏᴜR TᴀRɢᴇᴛ Cʜᴀᴛꜱ Iɴ HᴇRᴇ!",
       reply_markup=InlineKeyboardMarkup(buttons))
  elif type=="addchannel":
     await query.message.delete()
     try:
         text = await bot.send_message(user_id, "<b><u>Sᴇᴛ TᴀRɢᴇᴛ Cʜᴀᴛ</u></b>\n\nFᴏRᴡᴀRD A Mᴇꜱꜱᴀɢᴇ Fʀᴏᴍ YᴏᴜR TᴀRɢᴇᴛ Cʜᴀᴛ\n/cancel - Tᴏ Cᴀɴᴄᴇʟ Tʜɪꜱ Pʀᴏᴄᴇꜱꜱ")
         chat_ids = await bot.listen(chat_id=user_id, timeout=300)
         if chat_ids.text=="/cancel":
            await chat_ids.delete()
            return await text.edit_text(
                  "Pʀᴏᴄᴇꜱꜱ Cᴀɴᴄᴇʟʟᴇᴅ !",
                  reply_markup=InlineKeyboardMarkup(buttons))
         elif not chat_ids.forward_date:
            await chat_ids.delete()
            return await text.edit_text("Tʜɪꜱ Iꜱ Nᴏᴛ A FᴏRᴡᴀRDᴇᴅ Mᴇꜱꜱᴀɢᴇ!")
         else:
            chat_id = chat_ids.forward_from_chat.id
            title = chat_ids.forward_from_chat.title
            username = chat_ids.forward_from_chat.username
            username = "@" + username if username else "private"
         if await db.in_channel(user_id, chat_id):
             await chat_ids.delete()
             await text.edit_text(
                 "Tʜɪꜱ Cʜᴀɴɴᴇʟ Iꜱ AʟRᴇᴀᴅʏ Aᴅᴅᴇᴅ!",
                 reply_markup=InlineKeyboardMarkup(buttons))
         else:
             await db.add_channel(user_id, chat_id, title, username)
             await chat_ids.delete()
             await text.edit_text(
                 "Sᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ Uᴩᴅᴀᴛᴇᴅ ✓",
                 reply_markup=InlineKeyboardMarkup(buttons))
     except asyncio.exceptions.TimeoutError:
         await text.edit_text('Pʀᴏᴄᴇꜱꜱ Hᴀꜱ Bᴇᴇɴ Aᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ Cᴀɴᴄᴇʟʟᴇᴅ', reply_markup=InlineKeyboardMarkup(buttons))
  elif type.startswith("editbot"):
     bot_id = int(type.split('_')[1])
     _bot = await db.get_bot(user_id, bot_id)
     TEXT = Translation.BOT_DETAILS if _bot['is_bot'] else Translation.USER_DETAILS
     buttons = [[InlineKeyboardButton('⛒ Rᴇᴍᴏᴠᴇ ⛒', callback_data=f"settings#removebot_{_bot['id']}")
               ],
               [InlineKeyboardButton('⇇ Bᴀᴄᴋ', callback_data="settings#bots")]]
     await query.message.edit_text(
        TEXT.format(_bot['name'], _bot['id'], _bot['username']),
        reply_markup=InlineKeyboardMarkup(buttons))
  elif type.startswith("removebot"):
     bot_id = int(type.split('_')[1])
     await db.remove_bot(user_id, bot_id)
     await query.message.edit_text(
        "Sᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ Uᴩᴅᴀᴛᴇᴅ ✓",
        reply_markup=InlineKeyboardMarkup(buttons))
  elif type.startswith("editchannels"):
     chat_id = type.split('_')[1]
     chat = await db.get_channel_details(user_id, chat_id)
     buttons = [[InlineKeyboardButton('⛒ Rᴇᴍᴏᴠᴇ ⛒', callback_data=f"settings#removechannel_{chat_id}")
               ],
               [InlineKeyboardButton('⇇ Bᴀᴄᴋ', callback_data="settings#channels")]]
     await query.message.edit_text(
        f"<b><u>📄 Cʜᴀɴɴᴇʟ Dᴇᴛᴀɪʟꜱ</b></u>\n\n<b>Tɪᴛʟᴇ :</b> <code>{chat['title']}</code>\n<b>Cʜᴀɴɴᴇʟ ID :</b> <code>{chat['chat_id']}</code>\n<b>UsᴇRɴᴀᴍᴇ :</b> {chat['username']}",
        reply_markup=InlineKeyboardMarkup(buttons))
  elif type.startswith("removechannel"):
     chat_id = type.split('_')[1]
     await db.remove_channel(user_id, chat_id)
     await query.message.edit_text(
        "Sᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ Uᴩᴅᴀᴛᴇᴅ ✓",
        reply_markup=InlineKeyboardMarkup(buttons))
  elif type=="caption":
     buttons = []
     data = await get_configs(user_id)
     caption = data['caption']
     if caption is None:
        buttons.append([InlineKeyboardButton('⨁ Aᴅᴅ Cᴀᴩᴛɪᴏɴ ⨁',
                      callback_data="settings#addcaption")])
     else:
        buttons.append([InlineKeyboardButton('↳ Sᴇᴇ Cᴀᴩᴛɪᴏɴ',
                      callback_data="settings#seecaption")])
        buttons[-1].append(InlineKeyboardButton('↳ Dᴇʟᴇᴛᴇ Cᴀᴩᴛɪᴏɴ',
                      callback_data="settings#deletecaption"))
     buttons.append([InlineKeyboardButton('⇇ Bᴀᴄᴋ',
                      callback_data="settings#main")])
     await query.message.edit_text(
        "<b><u>Cᴜꜱᴛᴏᴍ Cᴀᴩᴛɪᴏɴ</b></u>\n\nYᴏᴜ Cᴀɴ Sᴇᴛ A Cᴜꜱᴛᴏᴍ Cᴀᴩᴛɪᴏɴ Tᴏ Vɪᴅᴇᴏꜱ Aɴᴅ Dᴏᴄᴜᴍᴇɴᴛꜱ. NᴏRᴍᴀʟʟʏ Usᴇ Iᴛꜱ Dᴇꜰᴀᴜʟᴛ Cᴀᴩᴛɪᴏɴ\n\n<b><u>Aᴠᴀɪʟᴀʙʟᴇ Fɪʟʟɪɴɢꜱ :</b></u>\n\n<code>{filename}</code> : Fɪʟᴇɴᴀᴍᴇ\n<code>{size}</code> : Fɪʟᴇ Sɪᴢᴇ\n<code>{caption}</code> : Dᴇꜰᴀᴜʟᴛ Cᴀᴩᴛɪᴏɴ",
        reply_markup=InlineKeyboardMarkup(buttons))
  elif type=="seecaption":
     data = await get_configs(user_id)
     buttons = [[InlineKeyboardButton('↳ Eᴅɪᴛ Cᴀᴩᴛɪᴏɴ',
                  callback_data="settings#addcaption")
               ],[
               InlineKeyboardButton('⇇ Bᴀᴄᴋ',
                 callback_data="settings#caption")]]
     await query.message.edit_text(
        f"<b><u>YᴏᴜR Cᴜꜱᴛᴏᴍ Cᴀᴩᴛɪᴏɴ</b></u>\n\n<code>{data['caption']}</code>",
        reply_markup=InlineKeyboardMarkup(buttons))
  elif type=="deletecaption":
     await update_configs(user_id, 'caption', None)
     await query.message.edit_text(
        "Successfully Button Deleted",
        reply_markup=InlineKeyboardMarkup(buttons))
  elif type=="addcaption":
     await query.message.delete()
     try:
         text = await bot.send_message(query.message.chat.id, "Send your custom caption\n/cancel - <code>cancel this process</code>")
         caption = await bot.listen(chat_id=user_id, timeout=300)
         if caption.text=="/cancel":
            await caption.delete()
            return await text.edit_text(
                  "Pʀᴏᴄᴇꜱꜱ Cᴀɴᴄᴇʟʟᴇᴅ !",
                  reply_markup=InlineKeyboardMarkup(buttons))
         try:
            caption.text.format(filename='', size='', caption='')
         except KeyError as e:
            await caption.delete()
            return await text.edit_text(
               f"Wrong Filling {e} UsᴇD Iɴ YᴏᴜR Cᴀᴩᴛɪᴏɴ. Cʜᴀɴɢᴇ Iᴛ",
               reply_markup=InlineKeyboardMarkup(buttons))
         await update_configs(user_id, 'caption', caption.text)
         await caption.delete()
         await text.edit_text(
            "Sᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ UsᴇD ✓",
            reply_markup=InlineKeyboardMarkup(buttons))
     except asyncio.exceptions.TimeoutError:
         await text.edit_text('Pʀᴏᴄᴇꜱꜱ Hᴀꜱ Bᴇᴇɴ Aᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ Cᴀɴᴄᴇʟʟᴇᴅ', reply_markup=InlineKeyboardMarkup(buttons))
  elif type=="button":
     buttons = []
     button = (await get_configs(user_id))['button']
     if button is None:
        buttons.append([InlineKeyboardButton('⨁ Aᴅᴅ Bᴜᴛᴛᴏɴ ⨁',
                      callback_data="settings#addbutton")])
     else:
        buttons.append([InlineKeyboardButton('↳ Sᴇᴇ Bᴜᴛᴛᴏɴ',
                      callback_data="settings#seebutton")])
        buttons[-1].append(InlineKeyboardButton('↳ Rᴇᴍᴏᴠᴇ Bᴜᴛᴛᴏɴ ',
                      callback_data="settings#deletebutton"))
     buttons.append([InlineKeyboardButton('⇇ Bᴀᴄᴋ',
                      callback_data="settings#main")])
     await query.message.edit_text(
        "<b><u>Cᴜꜱᴛᴏᴍ Bᴜᴛᴛᴏɴ</b></u>\n\nYᴏᴜ Cᴀɴ Sᴇᴛ Aɴ IɴLɪɴᴇ Bᴜᴛᴛᴏɴ Tᴏ Mᴇꜱꜱᴀɢᴇꜱ Wʜɪᴄʜ Wɪʟʟ Bᴇ FᴏRᴡᴀRDᴇᴅ.\n\n<b><u>FᴏRᴍᴀᴛ :</b></u>\n`[Mᴏᴅ Mᴏᴠɪᴇᴢ x][buttonurl:https://t.me/Mod_Moviez_X]`\n",
        reply_markup=InlineKeyboardMarkup(buttons))
  elif type=="addbutton":
     await query.message.delete()
     try:
         txt = await bot.send_message(user_id, text="**Send your custom button.\n\nFORMAT:**\n`[FᴏRᴡᴀRD ʙᴏᴛ][bᴜᴛᴛᴏɴᴜRL:ʜᴛᴛᴘs://ᴛ.ᴍᴇ/ᴋR_FᴏRᴡᴀRD_Bᴏᴛ]`\n")
         ask = await bot.listen(chat_id=user_id, timeout=300)
         button = parse_buttons(ask.text.html)
         if not button:
            await ask.delete()
            return await txt.edit_text("Iɴᴠᴀʟɪᴅ Bᴜᴛᴛᴏɴ ⛒")
         await update_configs(user_id, 'button', ask.text.html)
         await ask.delete()
         await txt.edit_text("Sᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ Bᴜᴛᴛᴏɴ Aᴅᴅᴇᴅ ✓",
            reply_markup=InlineKeyboardMarkup(buttons))
     except asyncio.exceptions.TimeoutError:
         await txt.edit_text('Pʀᴏᴄᴇꜱꜱ Hᴀꜱ Bᴇᴇɴ Aᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ Cᴀɴᴄᴇʟʟᴇᴅ', reply_markup=InlineKeyboardMarkup(buttons))
  elif type=="seebutton":
      button = (await get_configs(user_id))['button']
      button = parse_buttons(button, markup=False)
      button.append([InlineKeyboardButton("⇇ Bᴀᴄᴋ", "settings#button")])
      await query.message.edit_text(
         "**YᴏᴜR Cᴜꜱᴛᴏᴍ Bᴜᴛᴛᴏɴ**",
         reply_markup=InlineKeyboardMarkup(button))
  elif type=="deletebutton":
     await update_configs(user_id, 'button', None)
     await query.message.edit_text(
        "Successfully Button Deleted",
        reply_markup=InlineKeyboardMarkup(buttons))
  elif type=="database":
     buttons = []
     db_uri = (await get_configs(user_id))['db_uri']
     if db_uri is None:
        buttons.append([InlineKeyboardButton('⨁ Aᴅᴅ URL ⨁',
                      callback_data="settings#addurl")])
     else:
        buttons.append([InlineKeyboardButton('↳ Sᴇᴇ URL',
                      callback_data="settings#seeurl")])
        buttons[-1].append(InlineKeyboardButton('↳ Rᴇᴍᴏᴠᴇ URL',
                      callback_data="settings#deleteurl"))
     buttons.append([InlineKeyboardButton('⇇ Bᴀᴄᴋ',
                      callback_data="settings#main")])
     await query.message.edit_text(
        "<b><u>Dᴀᴛᴀʙᴀꜱᴇ</u></b>\n\nDᴀᴛᴀʙᴀꜱᴇ Iꜱ RᴇQᴜɪRᴇD FᴏR SᴛᴏRᴇ YᴏᴜR Dᴜᴩʟɪᴄᴀᴛᴇ Mᴇꜱꜱᴀɢᴇꜱ PᴇRᴍᴇɴᴀɴᴛ. OᴛʜᴇR Wɪꜱᴇ SᴛᴏRᴇD Dᴜᴩʟɪᴄᴀᴛᴇ Mᴇᴅɪᴀ Mᴀʏ Bᴇ DɪꜱᴀᴩᴩᴇᴀRᴇD Wʜᴇɴ AꜰᴛᴇR Bᴏᴛ RᴇꜱᴛᴀRᴛ.",
        reply_markup=InlineKeyboardMarkup(buttons))
  elif type=="addurl":
     await query.message.delete()
     uri = await bot.ask(user_id, "<b>please send your mongodb url.</b>\n\n<i>get your Mongodb url from [here](https://mongodb.com)</i>", disable_web_page_preview=True)
     if uri.text=="/cancel":
        return await uri.reply_text(
                  "Pʀᴏᴄᴇꜱꜱ Cᴀɴᴄᴇʟʟᴇᴅ !",
                  reply_markup=InlineKeyboardMarkup(buttons))
     if not uri.text.startswith("mongodb+srv://") and not uri.text.endswith("majority"):
        return await uri.reply("Iɴᴠᴀʟɪᴅ MᴏɴɢᴏDB URL ⛒, Aᴠᴏᴏᴅ '/' Iɴ Eɴᴅ Iꜰ TʜᴇRᴇ Iᴛ Iꜱ Aᴠᴀɪʟᴀʙʟᴇ",
                   reply_markup=InlineKeyboardMarkup(buttons))
     await update_configs(user_id, 'db_uri', uri.text)
     await uri.reply("Sᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ Dᴀᴛᴀʙᴀꜱᴇ URL Aᴅᴅᴇᴅ ✓",
             reply_markup=InlineKeyboardMarkup(buttons))
  elif type=="seeurl":
     db_uri = (await get_configs(user_id))['db_uri']
     await query.answer(f"Dᴀᴛᴀʙᴀꜱᴇ URL : {db_uri}", show_alert=True)
  elif type=="deleteurl":
     await update_configs(user_id, 'db_uri', None)
     await query.message.edit_text(
        "Successfully Your Database URL Deleted",
        reply_markup=InlineKeyboardMarkup(buttons))
  elif type=="filters":
     await query.message.edit_text(
        "<b><u>Cᴜꜱᴛᴏᴍ FɪʟᴛᴇRꜱ</u></b>\n\nCᴏɴꜰɪɢᴜRᴇ Tʜᴇ Tʏᴩᴇ Oꜰ Mᴇꜱꜱᴀɢᴇꜱ Wʜɪᴄʜ Yᴏᴜ Wᴀɴᴛ FᴏRᴡᴀRᴅ",
        reply_markup=await filters_buttons(user_id))
  elif type=="nextfilters":
     await query.edit_message.reply_markup(
        reply_markup=await next_filters_buttons(user_id))
  elif type.startswith("updatefilter"):
     i, key, value = type.split('-')
     if value=="True":
        await update_configs(user_id, key, False)
     else:
        await update_configs(user_id, key, True)
     if key in ['poll', 'protect']:
        return await query.edit_message.reply_markup(
           reply_markup=await next_filters_buttons(user_id))
     await query.edit_message.reply_markup(
        reply_markup=await filters_buttons(user_id))
  elif type.startswith("file_size"):
    settings = await get_configs(user_id)
    size = settings.get('file_size', 0)
    i, limit = size_limit(settings['size_limit'])
    await query.message.edit_text(
       f'<b><u>Sɪᴢᴇ Lɪᴍɪᴛ</u></b>\n\nYᴏᴜ Cᴀɴ Sᴇᴛ Fɪʟᴇ Sɪᴢᴇ Lɪᴍɪᴛ To FᴏRᴡᴀRD\n\nSᴛᴀᴛᴜꜱ : Fɪʟᴇꜱ Wɪᴛʜ {limit} `{size} ᴍʙ` Wɪʟʟ Bᴇ FᴏRᴡᴀRD',
       reply_markup=size_button(size))
  elif type.startswith("update_size"):
    size = int(query.data.split('-')[1])
    if 0 < size > 2000:
      return await query.answer("Size Limit Exceeded", show_alert=True)
    await update_configs(user_id, 'file_size', size)
    i, limit = size_limit((await get_configs(user_id))['size_limit'])
    await query.message.edit_text(
       f'<b><u>Sɪᴢᴇ Lɪᴍɪᴛ</u></b>\n\nYᴏᴜ FᴏRᴡᴀRD Tᴏ FᴏRᴡᴀRD\n\nSᴛᴀᴛᴜꜱ : Fɪʟᴇꜱ Wɪᴛʜ {limit} `{size} ᴍʙ` Wɪʟʟ FᴏRᴡᴀRD',
       reply_markup=size_button(int(size)))
  elif type.startswith('update_limit'):
    i, limit, size = type.split('-')
    limit, sts = size_limit(limit)
    await update_configs(user_id, 'size_limit', limit)
    await query.message.edit_text(
       f'<b><u>Size Limit</u></b>\n\nYou Can Set File Size Limit To Forward\n\nStatus : Files With {sts} `{size} MB` Will Forward',
       reply_markup=size_button(int(size)))
  elif type == "add_extension":
    await query.message.delete()
    ext = await bot.ask(user_id, text="Please Send Your Extensions (Seperete By Space)")
    if ext.text == '/cancel':
       return await ext.reply_text(
                  "Pʀᴏᴄᴇꜱꜱ Cᴀɴᴄᴇʟʟᴇᴅ !",
                  reply_markup=InlineKeyboardMarkup(buttons))
    extensions = ext.text.split(" ")
    extension = (await get_configs(user_id))['extension']
    if extension:
        for extn in extensions:
            extension.append(extn)
    else:
        extension = extensions
    await update_configs(user_id, 'extension', extension)
    await ext.reply_text(
        f"Sᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ Uᴩᴅᴀᴛᴇᴅ ✓",
        reply_markup=InlineKeyboardMarkup(buttons))
  elif type == "get_extension":
    extensions = (await get_configs(user_id))['extension']
    btn = extract_btn(extensions)
    btn.append([InlineKeyboardButton('⨁ Aᴅᴅ ⨁', 'settings#add_extension')])
    btn.append([InlineKeyboardButton('Rᴇᴍᴏᴠᴇ Aʟʟ', 'settings#rmve_all_extension')])
    btn.append([InlineKeyboardButton('⇇ Bᴀᴄᴋ', 'settings#main')])
    await query.message.edit_text(
        text='<b><u>Extensions</u></b>\n\nFiles With These Extiontions Will Not Forward',
        reply_markup=InlineKeyboardMarkup(btn))
  elif type == "rmve_all_extension":
    await update_configs(user_id, 'extension', None)
    await query.message.edit_text(text="Successfully Deleted",
                                   reply_markup=InlineKeyboardMarkup(buttons))
  elif type == "add_keyword":
    await query.message.delete()
    ask = await bot.ask(user_id, text="Please Send The Keywords (Seperete By Space)")
    if ask.text == '/cancel':
       return await ask.reply_text(
                  "Pʀᴏᴄᴇꜱꜱ Cᴀɴᴄᴇʟʟᴇᴅ !",
                  reply_markup=InlineKeyboardMarkup(buttons))
    keywords = ask.text.split(" ")
    keyword = (await get_configs(user_id))['keywords']
    if keyword:
        for word in keywords:
            keyword.append(word)
    else:
        keyword = keywords
    await update_configs(user_id, 'keywords', keyword)
    await ask.reply_text(
        f"Sᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ Uᴩᴅᴀᴛᴇᴅ ✓",
        reply_markup=InlineKeyboardMarkup(buttons))
  elif type == "get_keyword":
    keywords = (await get_configs(user_id))['keywords']
    btn = extract_btn(keywords)
    btn.append([InlineKeyboardButton('⨁ Aᴅᴅ ⨁', 'settings#add_keyword')])
    btn.append([InlineKeyboardButton('Rᴇᴍᴏᴠᴇ Aʟʟ', 'settings#rmve_all_keyword')])
    btn.append([InlineKeyboardButton('⇇ Bᴀᴄᴋ', 'settings#main')])
    await query.message.edit_text(
        text='<b><u>Keywords</u></b>\n\nFile With These Keywords In File Name Will FᴏRᴡᴀRD',
        reply_markup=InlineKeyboardMarkup(btn))
  elif type == "rmve_all_keyword":
    await update_configs(user_id, 'keywords', None)
    await query.message.edit_text(text="Successfully Deleted",
                                   reply_markup=InlineKeyboardMarkup(buttons))
  elif type.startswith("alert"):
    alert = type.split('_')[1]
    await query.answer(alert, show_alert=True)
def main_buttons():
  buttons = [[
       InlineKeyboardButton('⚹ Bᴏᴛꜱ',
                    callback_data=f'settings#bots'),
       InlineKeyboardButton('Cʜᴀɴɴᴇʟꜱ ⚹',
                    callback_data=f'settings#channels')
       ],[
       InlineKeyboardButton('⚹ Cᴀᴩᴛɪᴏɴ',
                    callback_data=f'settings#caption'),
       InlineKeyboardButton('MᴏɴɢᴏDB ⚹',
                    callback_data=f'settings#database')
       ],[
       InlineKeyboardButton('⚹ FɪʟᴛᴇRꜱ',
                    callback_data=f'settings#filters'),
       InlineKeyboardButton('Bᴜᴛᴛᴏɴ ⚹',
                    callback_data=f'settings#button')
       ],[
       InlineKeyboardButton('⛭ Exᴛʀꜱ SᴇᴛᴛɪɴGS ⛭',
                    callback_data='settings#nextfilters')
       ],[
       InlineKeyboardButton('⇇ Bᴀᴄᴋ', callback_data='back')
       ]]
  return InlineKeyboardMarkup(buttons)
def size_limit(limit):
   if str(limit) == "None":
      return None, ""
   elif str(limit) == "True":
      return True, "more than"
   else:
      return False, "less than"
def extract_btn(datas):
    i = 0
    btn = []
    if datas:
       for data in datas:
         if i >= 5:
            i = 0
         if i == 0:
            btn.append([InlineKeyboardButton(data, f'settings#alert_{data}')])
            i += 1
            continue
         elif i > 0:
            btn[-1].append(InlineKeyboardButton(data, f'settings#alert_{data}'))
            i += 1
    return btn
def size_button(size):
  buttons = [[
       InlineKeyboardButton('+',
                    callback_data=f'settings#update_limit-True-{size}'),
       InlineKeyboardButton('=',
                    callback_data=f'settings#update_limit-None-{size}'),
       InlineKeyboardButton('-',
                    callback_data=f'settings#update_limit-False-{size}')
       ],[
       InlineKeyboardButton('+1',
                    callback_data=f'settings#update_size-{size + 1}'),
       InlineKeyboardButton('-1',
                    callback_data=f'settings#update_size_-{size - 1}')
       ],[
       InlineKeyboardButton('+5',
                    callback_data=f'settings#update_size-{size + 5}'),
       InlineKeyboardButton('-5',
                    callback_data=f'settings#update_size_-{size - 5}')
       ],[
       InlineKeyboardButton('+10',
                    callback_data=f'settings#update_size-{size + 10}'),
       InlineKeyboardButton('-10',
                    callback_data=f'settings#update_size_-{size - 10}')
       ],[
       InlineKeyboardButton('+50',
                    callback_data=f'settings#update_size-{size + 50}'),
       InlineKeyboardButton('-50',
                    callback_data=f'settings#update_size_-{size - 50}')
       ],[
       InlineKeyboardButton('+100',
                    callback_data=f'settings#update_size-{size + 100}'),
       InlineKeyboardButton('-100',
                    callback_data=f'settings#update_size_-{size - 100}')
       ],[
       InlineKeyboardButton('↩ Bᴀᴄᴋ',
                    callback_data="settings#main")
     ]]
  return InlineKeyboardMarkup(buttons)

async def filters_buttons(user_id):
  filter = await get_configs(user_id)
  filters = filter['filters']
  buttons = [[
       InlineKeyboardButton('🏷️ FᴏRᴡᴀRD Tᴀɢ',
                    callback_data=f'settings_#updatefilter-forward_tag-{filter["forward_tag"]}'),
       InlineKeyboardButton('✅' if filter['forward_tag'] else '❌',
                    callback_data=f'settings#updatefilter-forward_tag-{filter["forward_tag"]}')
       ],[
       InlineKeyboardButton('🖍️ Tᴇxᴛ',
                    callback_data=f'settings_#updatefilter-text-{filters["text"]}'),
       InlineKeyboardButton('✅' if filters['text'] else '❌',
                    callback_data=f'settings#updatefilter-text-{filters["text"]}')
       ],[
       InlineKeyboardButton('📁 Dᴏᴄᴜᴍᴇɴᴛꜱ',
                    callback_data=f'settings_#updatefilter-document-{filters["document"]}'),
       InlineKeyboardButton('✅' if filters['document'] else '❌',
                    callback_data=f'settings#updatefilter-document-{filters["document"]}')
       ],[
       InlineKeyboardButton('🎞️ Vɪᴅᴇᴏꜱ',
                    callback_data=f'settings_#updatefilter-video-{filters["video"]}'),
       InlineKeyboardButton('✅' if filters['video'] else '❌',
                    callback_data=f'settings#updatefilter-video-{filters["video"]}')
       ],[
       InlineKeyboardButton('📷 Pʜᴏᴛᴏꜱ',
                    callback_data=f'settings_#updatefilter-photo-{filters["photo"]}'),
       InlineKeyboardButton('✅' if filters['photo'] else '❌',
                    callback_data=f'settings#updatefilter-photo-{filters["photo"]}')
       ],[
       InlineKeyboardButton('🎧 Aᴜᴅɪᴏ',
                    callback_data=f'settings_#updatefilter-audio-{filters["audio"]}'),
       InlineKeyboardButton('✅' if filters['audio'] else '❌',
                    callback_data=f'settings#updatefilter-audio-{filters["audio"]}')
       ],[
       InlineKeyboardButton('🎤 Vᴏɪᴄᴇ',
                    callback_data=f'settings_#updatefilter-voice-{filters["voice"]}'),
       InlineKeyboardButton('✅' if filters['voice'] else '❌',
                    callback_data=f'settings#updatefilter-voice-{filters["voice"]}')
       ],[
       InlineKeyboardButton('🎭 Aɴɪᴍᴀᴛɪᴏɴ',
                    callback_data=f'settings_#updatefilter-animation-{filters["animation"]}'),
       InlineKeyboardButton('✅' if filters['animation'] else '❌',
                    callback_data=f'settings#updatefilter-animation-{filters["animation"]}')
       ],[
       InlineKeyboardButton('🃏 SᴛɪᴄᴋᴇRꜱ',
                    callback_data=f'settings_#updatefilter-sticker-{filters["sticker"]}'),
       InlineKeyboardButton('✅' if filters['sticker'] else '❌',
                    callback_data=f'settings#updatefilter-sticker-{filters["sticker"]}')
       ],[
       InlineKeyboardButton('▶️ Sᴋɪᴩ Dᴜᴩʟɪᴄᴀᴛᴇ',
                    callback_data=f'settings_#updatefilter-duplicate-{filter["duplicate"]}'),
       InlineKeyboardButton('✅' if filter['duplicate'] else '❌',
                    callback_data=f'settings#updatefilter-duplicate-{filter["duplicate"]}')
       ],[
       InlineKeyboardButton('⇇ Bᴀᴄᴋ',
                    callback_data="settings#main")
       ]]
  return InlineKeyboardMarkup(buttons)

async def next_filters_buttons(user_id):
  filter = await get_configs(user_id)
  filters = filter['filters']
  buttons = [[
       InlineKeyboardButton('📊 Pᴏʟʟ',
                    callback_data=f'settings_#updatefilter-poll-{filters["poll"]}'),
       InlineKeyboardButton('✅' if filters['poll'] else '❌',
                    callback_data=f'settings#updatefilter-poll-{filters["poll"]}')
       ],[
       InlineKeyboardButton('🔒 SᴇᴄᴜRᴇ Mᴇꜱꜱᴀɢᴇ',
                    callback_data=f'settings_#updatefilter-protect-{filter["protect"]}'),
       InlineKeyboardButton('✅' if filter['protect'] else '❌',
                    callback_data=f'settings#updatefilter-protect-{filter["protect"]}')
       ],[
       InlineKeyboardButton('🛑 Sɪᴢᴇ Lɪᴍɪᴛ',
                    callback_data='settings#file_size')
       ],[
       InlineKeyboardButton('💾 Exᴛᴇɴꜱɪᴏɴ',
                    callback_data='settings#get_extension')
       ],[
       InlineKeyboardButton('📌 KᴇʏᴡᴏRᴅꜱ',
                    callback_data='settings#get_keyword')
       ],[
       InlineKeyboardButton('⇇ Bᴀᴄᴋ',
                    callback_data="settings#main")
       ]]
  return InlineKeyboardMarkup(buttons)

# plugins/test.py
BTN_URL_REGEX = re.compile(r"(\[([^\[]+?)]\[buttonurl:/{0,2}(.+?)(:same)?])")
BOT_TOKEN_TEXT = "1) Cʀᴇᴀᴛᴇ A Bᴏᴛ Usɪɴɢ @BotFather [ꜱᴇɴᴅ <code>/newbot</code> ᴛᴏ ʙᴏᴛ ꜰᴀᴛʜᴇR ᴀɴᴅ ᴛʜᴇ ɴᴀᴍᴇ ᴀɴᴅ ᴜꜱᴇRɴᴀᴍᴇ Rᴇꜱᴩᴇᴄᴛɪᴠᴇʟʏ]\n\n2) Tʜᴇɴ Yᴏᴜ Wɪʟʟ Gᴇᴛ A Mᴇꜱꜱᴀɢᴇ Wɪᴛʜ Bᴏᴛ Tᴏᴋᴇɴ\n\n3) FᴏRᴡᴀRD Tʜᴀᴛ Mᴇꜱꜱᴀɢᴇ Tᴏ Mᴇ \n\nIꜰ Yᴏᴜ Hᴀᴠᴇ A Bᴏᴛ AʟRᴇᴀᴅʏ, Yᴏᴜ Cᴀɴ FᴏRᴡᴀRD Iᴛꜱ Tᴏᴋᴇɴ Fʀᴏᴍ API Bᴏᴛ Tᴏᴋᴇɴ."
SESSION_STRING_SIZE = 351

async def start_clone_bot(FwdBot):
   await FwdBot.start()
   return FwdBot

class CLIENT:
  def __init__(self):
     self.api_id = Config.API_ID
     self.api_hash = Config.API_HASH

  def client(self, data, user=None):
     if user == None and data.get('is_bot') == False:
        return Client("USERBOT", self.api_id, self.api_hash, session_string=data.get('session'))
     elif user == True:
        return Client("USERBOT", self.api_id, self.api_hash, session_string=data)
     elif user != False:
        data = data.get('token')
     return Client("BOT", self.api_id, self.api_hash, bot_token=data, in_memory=True)

async def add_bot(bot, message):
     user_id = int(message.from_user.id)
     msg = await bot.ask(chat_id=user_id, text=BOT_TOKEN_TEXT)
     if msg.text=='/cancel':
        return await msg.reply('<b>Pʀᴏᴄᴇꜱꜱ Cᴀɴᴄᴇʟʟᴇᴅ !</b>')
     elif not msg.forward_date:
       return await msg.reply_text("Tʜɪꜱ Iꜱ Nᴏᴛ FᴏRᴡᴀRDᴇᴅ Mᴇꜱꜱᴀɢᴇ !")
     elif str(msg.forward_from.id) != "93372553":
       return await msg.reply_text("Tʜɪꜱ Mᴇꜱꜱᴀɢᴇ Wᴀꜱ Nᴏᴛ FᴏRᴡᴀRDᴇᴅ Fʀᴏᴍ Tʜᴇ Bᴏᴛ FᴀᴛʜᴇR !")
     bot_token = re.findall(r'\d[0-9]{8,10}:[0-9A-Za-z_-]{35}', msg.text, re.IGNORECASE)
     bot_token = bot_token[0] if bot_token else None
     if not bot_token:
       return await msg.reply_text("TʜᴇRᴇ Iꜱ Nᴏ Bᴏᴛ Tᴏᴋᴇɴ Iɴ Tʜᴀᴛ Mᴇꜱꜱᴀɢᴇ !Tʀʏ Aɢᴀɪɴ Pʟᴇᴀꜱᴇ !")
     try:
       _client = await start_clone_bot(CLIENT().client(bot_token, False))
     except Exception as e:
       await msg.reply_text(f"Bᴏᴛ EʀʀᴏR :</b> `{e}` /nFᴏRᴡᴀRD ɪᴛ ᴛᴏ @Syd_Xyz Iꜰ ʏᴏᴜ ɴᴇᴇᴅ Hᴇʟᴩ !")
     _bot = _client.me
     details = {
       'id': _bot.id,
       'is_bot': True,
       'user_id': user_id,
       'name': _bot.first_name,
       'token': bot_token,
       'username': _bot.username
     }
     await db.add_bot(user_id, details)
     return True

async def add_session(bot, message):
     user_id = int(message.from_user.id)
     text = "<b>⚠️ DɪꜱᴄʟᴀɪᴍᴇR ⚠️</b>\n\nYᴏᴜ Cᴀɴ Usᴇ YᴏᴜR Sᴇꜱꜱɪᴏɴ FᴏR FᴏRᴡᴀRDɪɴɢ Mᴇꜱꜱᴀɢᴇ Fʀᴏᴍ Pʀɪᴠᴀᴛᴇ Cʜᴀᴛ Tᴏ AɴᴏᴛʜᴇR Cʜᴀᴛ.\nPʟᴇᴀꜱᴇ Aᴅᴅ Yᴏᴜʀ <b><u>PʏRᴏɢRᴀᴍ Sᴇꜱꜱɪᴏɴ</u> Wɪᴛʜ YᴏᴜR Oᴡɴ Rɪꜱᴋ </b>. TʜᴇRᴇ Iꜱ A Cʜᴀɴᴄᴇ Tᴏ Bᴀɴ YᴏᴜR Aᴄᴄᴏᴜɴᴛ (ꜱᴏ, ꜰᴏRᴡᴀRDɪɴɢ ᴡɪʟʟ ʙᴇ ʟɪɪᴛʟᴇ ꜱʟᴏᴡ). Mʏ DᴇᴠᴇʟᴏᴩᴇR <b>Iꜱ Nᴏᴛ Rᴇꜱᴩᴏɴꜱɪʙʟᴇ Iꜰ YᴏᴜR Aᴄᴄᴏᴜɴᴛ Mᴀʏ Gᴇᴛ Bᴀɴɴᴇᴅ! /nUsᴇ Tʜᴇ Aᴄᴄᴏᴜɴᴛ Wɪᴛʜ Wʜɪᴄʜ Yᴏᴜ Cᴀɴ Rɪꜱᴋ(Nᴏᴛ IᴍᴩᴏRᴛᴀɴᴛ).</b>"
     await bot.send_message(user_id, text=text)
     msg = await bot.ask(chat_id=user_id, text="<b>Sᴇɴᴅ ʏᴏᴜʀ ᴩʏʀᴏɢʀᴀᴍ ꜱᴇꜱꜱɪᴏɴ.\nɢᴇᴛ ɪᴛ ғʀᴏᴍ @mdsessiongenbot\n\n/cancel - ᴄᴀɴᴄᴇʟ ᴛʜᴇ ᴩʀᴏᴄᴇꜱꜱ</b>")
     if msg.text=='/cancel':
        return await msg.reply('<b>Pʀᴏᴄᴇꜱꜱ Cᴀɴᴄᴇʟʟᴇᴅ !</b>')
     elif len(msg.text) < SESSION_STRING_SIZE:
        return await msg.reply('Iɴᴠᴀʟɪᴅ Sᴇꜱꜱɪᴏɴ SᴛRɪɴɢ !')
     try:
       client = await start_clone_bot(CLIENT().client(msg.text, True))
     except Exception as e:
       await msg.reply_text(f"<b>UsᴇR Bᴏᴛ EʀʀᴏR :</b> `{e}` /nFᴏRᴡᴀRD ɪᴛ ᴛᴏ @Syd_Xyz Iꜰ ʏᴏᴜ ɴᴇᴇᴅ Hᴇʟᴩ !")
     user = client.me
     details = {
       'id': user.id,
       'is_bot': False,
       'user_id': user_id,
       'name': user.first_name,
       'session': msg.text,
       'username': user.username
     }
     await db.add_bot(user_id, details)
     return True

@Client.on_message(filters.private & filters.command('reset'))
async def forward_tag(bot, m):
    default = await db.get_configs("01")
    await db.update_configs(m.from_user.id, default)
    await m.reply("Sᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ Sᴇᴛᴛɪɴɢꜱ Rᴇꜱᴇᴛᴇᴅ ✔️")

@Client.on_message(filters.command('resetall') & filters.user(Config.OWNER_ID))
async def resetall(bot, message):
  users = await db.get_all_users()
  sts = await message.reply("Processing")
  TEXT = "Tᴏᴛᴀʟ: {}\nSᴜᴄᴄᴇꜱꜱ: {}\nFᴀɪʟᴇᴅ: {}\nExᴄᴇᴩᴛ: {}"
  total = success = failed = already = 0
  ERRORS = []
  async for user in users:
      user_id = user['id']
      default = await get_configs(user_id)
      default['db_uri'] = None
      total += 1
      if total %10 == 0:
         await sts.edit(TEXT.format(total, success, failed, already))
      try:
         await db.update_configs(user_id, default)
         success += 1
      except Exception as e:
         ERRORS.append(e)
         failed += 1
  if ERRORS:
     await message.reply(ERRORS[:100])
  await sts.edit("Cᴏᴍᴩʟᴇᴛᴇᴅ\n" + TEXT.format(total, success, failed, already))

async def get_configs(user_id):
  configs = await db.get_configs(user_id)
  if 'forward_delay' not in configs:
      configs['forward_delay'] = 1.0
  return configs

async def update_configs(user_id, key, value):
  current = await db.get_configs(user_id)
  if key in ['caption', 'duplicate', 'db_uri', 'forward_tag', 'protect', 'file_size', 'size_limit', 'extension', 'keywords', 'button', 'forward_delay']:
     current[key] = value
  else:
     current['filters'][key] = value
  await db.update_configs(user_id, current)

def parse_buttons(text, markup=True):
    buttons = []
    for match in BTN_URL_REGEX.finditer(text):
        n_escapes = 0
        to_check = match.start(1) - 1
        while to_check > 0 and text[to_check] == "\\":
            n_escapes += 1
            to_check -= 1
        if n_escapes % 2 == 0:
            if bool(match.group(4)) and buttons:
                buttons[-1].append(InlineKeyboardButton(
                    text=match.group(2),
                    url=match.group(3).replace(" ", "")))
            else:
                buttons.append([InlineKeyboardButton(
                    text=match.group(2),
                    url=match.group(3).replace(" ", ""))])
    if markup and buttons:
       buttons = InlineKeyboardMarkup(buttons)
    return buttons if buttons else None
