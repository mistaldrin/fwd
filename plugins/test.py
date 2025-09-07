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

BOT_TOKEN_TEXT = "1. Go to @BotFather and send `/newbot`.\n\n2. Get the bot token from the reply.\n\n3. Forward that message here or just send the token.\n\nEasy peasy. (´｡• ᵕ •｡`)"
SESSION_STRING_SIZE = 351

async def start_clone_bot(FwdBot, data=None):
   """Starts the client and patches the iter_messages method."""
   await FwdBot.start()
   
   async def iter_messages(
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
            messages = await self.get_messages(chat_id, list(range(current, current+new_diff+1)))
            for message in messages:
                yield message
                current += 1

   FwdBot.iter_messages = iter_messages.__get__(FwdBot, Client)
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
  
  async def add_bot(self, bot, message: Message):
     """Handles the conversation flow for adding a new bot."""
     user_id = int(message.from_user.id)
     msg = await bot.ask(chat_id=user_id, text=BOT_TOKEN_TEXT)
     
     if msg.text == '/cancel':
        return await msg.reply('Process cancelled.')

     bot_token_match = re.findall(r'(\d{8,10}:[a-zA-Z0-9_-]{35})', msg.text)
     bot_token = bot_token_match[0] if bot_token_match else None

     if not bot_token:
       return await msg.reply_text("No valid bot token found.")

     try:
       async with self.client(bot_token) as _client:
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
    
  async def add_session(self, bot, message: Message):
     """Handles the conversation flow for adding a new userbot session."""
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
