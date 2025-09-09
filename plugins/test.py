#1
import os
import re 
import sys
import typing
import asyncio 
import logging 
from uuid import uuid4
from database import db 
from config import Config, temp
from pyrogram import Client, filters, types
from pyrogram.raw.all import layer
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, Message 
from pyrogram.errors.exceptions.bad_request_400 import AccessTokenExpired, AccessTokenInvalid
from pyrogram.errors import FloodWait
from config import Config
from translation import Translation

from typing import Union, Optional, AsyncGenerator

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

BOT_TOKEN_TEXT = "1. Go to @BotFather and send `/newbot`.\n\n2. Get the bot token from the reply.\n\n3. Forward that message here or just send the token.\n\n/cancel - to cancel."
SESSION_STRING_TEXT = "<b>A friendly heads-up!</b> (｡•̀ᴗ-)✧\n\nUsing a user account for automation can be risky. It's a good idea to use an alternate account for this.\n\nThe developer is not responsible for what happens.\n\n<b>Send the Pyrogram (v2) session string.</b>\n\nGet one from @mdsessiongenbot.\n\n/cancel - to cancel."
SESSION_STRING_SIZE = 351
BTN_URL_REGEX = re.compile(r"(\[([^\[]+?)]\[buttonurl:/{0,2}(.+?)(:same)?])")


def parse_buttons(text, markup=True):
    """Parses button markdown into a Pyrogram InlineKeyboardMarkup."""
    buttons = []
    if not text:
        return None
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

async def start_clone_bot(FwdBot, bot_data):
   """Starts the client and patches the iter_messages method for bot compatibility."""
   await FwdBot.start()
   
   # This is the bot-compatible message iterator from mr-syd.
   # 'self' will be the client instance, passed implicitly by __get__.
   async def iter_messages_fixed(
      self, 
      chat_id: Union[int, str], 
      limit: int, 
      offset: int = 0
      ) -> Optional[AsyncGenerator["types.Message", None]]:
        current = offset
        while True:
            new_diff = min(200, limit - current)
            if new_diff <= 0:
                return

            messages = await self.get_messages(chat_id, list(range(current, current + new_diff + 1)))
            
            for message in messages:
                yield message
                current += 1

   # Correctly bind the function as a method to the client instance if it's a bot.
   if bot_data.get('is_bot', False):
       FwdBot.iter_messages = iter_messages_fixed.__get__(FwdBot, Client)
   
   return FwdBot

class CLIENT: 
  def __init__(self):
     self.api_id = Config.API_ID
     self.api_hash = Config.API_HASH
    
  def client(self, data, user=None):
     """Creates a Pyrogram client instance."""
     client_name = str(uuid4())
     if user is None and isinstance(data, dict) and not data.get('is_bot'):
        return Client(name=client_name, api_id=self.api_id, api_hash=self.api_hash, session_string=data.get('session'), in_memory=True)
     elif user is True:
        return Client(name=client_name, api_id=self.api_id, api_hash=self.api_hash, session_string=data, in_memory=True)
     else:
        token = data.get('token') if isinstance(data, dict) else data
        return Client(name=client_name, api_id=self.api_id, api_hash=self.api_hash, bot_token=token, in_memory=True)
  
  async def add_bot(self, bot, query: Union[Message, CallbackQuery]):
     """Handles the conversation flow for adding a new bot."""
     user_id = query.from_user.id
     try:
        msg = await bot.ask(chat_id=user_id, text=BOT_TOKEN_TEXT, timeout=300)
        
        if msg.text and msg.text.lower() == '/cancel':
           return await msg.reply('Process cancelled.')

        bot_token_match = re.search(r'(\d{8,10}:[a-zA-Z0-9_-]{35})', msg.text)
        bot_token = bot_token_match.group(1) if bot_token_match else None

        if not bot_token:
          return await msg.reply_text("No valid bot token found.")

        try:
          async with self.client(bot_token) as _client:
             _bot = await _client.get_me()
        except Exception as e:
          return await msg.reply_text(f"<b>Bot Error:</b> `{e}`\n\nPlease check the token.")
        
        if await db.is_bot_exist(user_id, _bot.id):
            return await msg.reply_text("This bot has already been added.")

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
     except asyncio.TimeoutError:
        await bot.send_message(user_id, "Process timed out.")
        return False
    
  async def add_session(self, bot, query: Union[Message, CallbackQuery]):
     """Handles the conversation flow for adding a new userbot session."""
     user_id = query.from_user.id
     try:
        msg = await bot.ask(chat_id=user_id, text=SESSION_STRING_TEXT, timeout=300)

        if msg.text and msg.text.lower() == '/cancel':
           await msg.reply('Process cancelled.')
           return False
        elif not msg.text or len(msg.text) < SESSION_STRING_SIZE:
           return await msg.reply('Not a valid session string.')

        try:
          async with self.client(msg.text, True) as client:
             user = await client.get_me()
        except Exception as e:
          return await msg.reply_text(f"<b>Userbot Error:</b> `{e}`\n\nPlease check the session string.")
        
        if await db.is_bot_exist(user_id, user.id):
            return await msg.reply_text("This userbot has already been added.")

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
     except asyncio.TimeoutError:
        await bot.send_message(user_id, "Process timed out.")
        return False

@Client.on_message(filters.private & filters.command('reset'))
async def reset_user_settings(bot, m):
    """Resets a user's settings to default."""
    default = await db.get_configs("01")
    await db.update_configs(m.from_user.id, default)
    await m.reply("Settings have been reset. ✓")

@Client.on_message(filters.command('resetall') & filters.user(Config.OWNER_ID))
async def reset_all_users_settings(bot, message):
    """(Owner only) Resets specific settings for all users."""
    users = await db.get_all_users()
    sts = await message.reply("Processing...")
    TEXT = "Total: {}\nSuccess: {}\nFailed: {}"
    total = success = failed = 0
    ERRORS = []
    async for user in users:
        user_id = user['id']
        default = await get_configs(user_id)
        default['db_uri'] = None
        total += 1
        if total % 10 == 0:
           await sts.edit(TEXT.format(total, success, failed))
        try: 
           await db.update_configs(user_id, default)
           success += 1
        except Exception as e:
           ERRORS.append(e)
           failed += 1
    if ERRORS:
       await message.reply(ERRORS[:100])
    await sts.edit("Completed\n" + TEXT.format(total, success, failed))
  
async def get_configs(user_id):
    """Retrieves user configurations from the database."""
    return await db.get_configs(user_id)

async def update_configs(user_id, key, value):
    """Updates a specific configuration key for a user."""
    current = await db.get_configs(user_id)
    if key in ['caption', 'duplicate', 'db_uri', 'forward_tag', 'protect', 'file_size', 'size_limit', 'extension', 'keywords', 'button', 'forward_delay']:
       current[key] = value
    elif key in current.get('filters', {}):
       current['filters'][key] = value
    await db.update_configs(user_id, current)
