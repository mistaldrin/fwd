import os
import re 
import sys
import typing
import asyncio 
import logging 
from uuid import uuid4
from database import db 
from config import Config, temp
from pyrogram import Client, filters
from pyrogram.raw.all import layer
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, Message 
from pyrogram.errors.exceptions.bad_request_400 import AccessTokenExpired, AccessTokenInvalid
from pyrogram.errors import FloodWait
from config import Config
from translation import Translation

from typing import Union, Optional, AsyncGenerator

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

BOT_TOKEN_TEXT = "To add a bot, send its token or forward the message from @BotFather.\n\n/cancel - to cancel."
SESSION_STRING_SIZE = 351


class CLIENT: 
  def __init__(self):
     self.api_id = Config.API_ID
     self.api_hash = Config.API_HASH
    
  def client(self, data, user=None):
     # Give each client a unique name to avoid conflicts
     client_name = str(uuid4())
     
     # Userbot client from session dictionary (used by /forward)
     if user is None and isinstance(data, dict) and not data.get('is_bot'):
        return Client(name=client_name, api_id=self.api_id, api_hash=self.api_hash, session_string=data.get('session'), in_memory=True)
     
     # Userbot client from session string (used by /unequify, /ubclist)
     elif user is True:
        return Client(name=client_name, api_id=self.api_id, api_hash=self.api_hash, session_string=data, in_memory=True)
     
     # Bot client from token
     else:
        token = data.get('token') if isinstance(data, dict) else data
        return Client(name=client_name, api_id=self.api_id, api_hash=self.api_hash, bot_token=token, in_memory=True)
  
  async def add_bot(self, bot, message):
     user_id = int(message.from_user.id)
     msg = await bot.ask(chat_id=user_id, text=BOT_TOKEN_TEXT)
     if msg.text=='/cancel':
        return await msg.reply('Process cancelled.')

     # Use regex to find a token in the message text
     bot_token_match = re.search(r'(\d+:[a-zA-Z0-9_-]{35})', msg.text)

     if not bot_token_match:
        return await msg.reply_text("No valid bot token found.")

     bot_token = bot_token_match.group(1)
     
     try:
       async with self.client(bot_token, False) as _client:
          _bot = await _client.get_me()
     except Exception as e:
       return await msg.reply_text(f"<b>Bot Error:</b> `{e}`\n\nPlease check the token.")
     
     details = {
       'id': _bot.id,
       'is_bot': True,
       'user_id': user_id,
       'name': _bot.first_name,
       'token': bot_token,
       'username': _bot.username 
     }
     await db.add_bot(details)
     return True
    
  async def add_session(self, bot, message):
     user_id = int(message.from_user.id)
     text = "<b>A friendly heads-up!</b> (｡•̀ᴗ-)✧\n\nUsing a user account for automation can be risky. It's a good idea to use an alternate account for this.\n\nThe developer is not responsible for what happens."
     await bot.send_message(user_id, text=text)
     msg = await bot.ask(chat_id=user_id, text="<b>Send the Pyrogram (v2) session string.</b>\n\nGet one from @mdsessiongenbot.\n\n/cancel - to cancel.")
     if msg.text=='/cancel':
        return await msg.reply('Process cancelled.')
     elif len(msg.text) < SESSION_STRING_SIZE:
        return await msg.reply('Not a valid session string.')
     try:
       async with self.client(msg.text, True) as client:
          user = await client.get_me()
     except Exception as e:
       return await msg.reply_text(f"<b>Userbot Error:</b> `{e}`\n\nPlease check the session string.")
     
     details = {
       'id': user.id,
       'is_bot': False,
       'user_id': user_id,
       'name': user.first_name,
       'session': msg.text,
       'username': user.username
     }
     await db.add_bot(details)
     return True
    
@Client.on_message(filters.private & filters.command('reset'))
async def forward_tag(bot, m):
    default = await db.get_configs("01")
    await db.update_configs(m.from_user.id, default)
    await m.reply("Settings have been reset. ✓")

@Client.on_message(filters.command('resetall') & filters.user(Config.OWNER_ID))
async def resetall(bot, message):
  users = await db.get_all_users()
  sts = await message.reply("Processing...")
  TEXT = "Total: {}\nSuccess: {}\nFailed: {}\nExcept: {}"
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
  await sts.edit("Completed\n" + TEXT.format(total, success, failed, already))
  
async def get_configs(user_id):
  configs = await db.get_configs(user_id)
  # Add default for the new forward_delay setting
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
