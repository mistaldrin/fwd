# mistaldrin/fwd/fwd-dawn-improve-v2/plugins/test.py
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
   # It is more efficient than get_messages for large ranges.
   async def iter_messages_fixed(
      self, 
      chat_id: Union[int, str],
      limit: int = 0,
      offset: int = 0,
      reverse: bool = False
      ) -> Optional[AsyncGenerator["types.Message", None]]:
        
        total = 0
        
        if not reverse:
            # History is fetched from newest to oldest by default
            async for message in self.get_chat_history(chat_id, limit=0 if limit == 0 else (limit + offset)):
                if total < offset:
                    total += 1
                    continue
                yield message
                total += 1
                if limit != 0 and total >= (limit + offset):
                    break
        else:
            # To get messages from oldest to newest, we need to get the count first
            count = await self.get_chat_history_count(chat_id)
            
            # Start from the calculated offset from the end
            for i in range(count - offset, 0, -100):
                if temp.CANCEL.get(self.me.id): # A way to cancel long fetches
                    break
                
                messages = await self.get_messages(chat_id, list(range(max(1, i - 99), i + 1)))
                
                for message in sorted(messages, key=lambda x: x.id):
                    yield message
                    total += 1
                    if limit != 0 and total >= limit:
                        return # Exit the generator
                
                if limit != 0 and total >= limit:
                    break
   
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
     msg = query # We no longer use bot.ask, we process the message directly
     
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
       'id': _bot.id, 'is_bot': True, 'user_id': user_id,
       'name': _bot.first_name, 'token': bot_token, 'username': _bot.username 
     }
     await db.add_bot(details)
     await msg.reply_text("Bot token added. ✓")

    
  async def add_session(self, bot, query: Union[Message, CallbackQuery]):
     """Handles the conversation flow for adding a new userbot session."""
     user_id = query.from_user.id
     msg = query
     
     if not msg.text or len(msg.text) < SESSION_STRING_SIZE:
        return await msg.reply('Not a valid session string.')

     try:
       async with self.client(msg.text, True) as client:
          user = await client.get_me()
     except Exception as e:
       return await msg.reply_text(f"<b>Userbot Error:</b> `{e}`\n\nPlease check the session string.")
     
     if await db.is_bot_exist(user_id, user.id):
         return await msg.reply_text("This userbot has already been added.")

     details = {
       'id': user.id, 'is_bot': False, 'user_id': user_id,
       'name': user.first_name, 'session': msg.text, 'username': user.username
     }
     await db.add_bot(details)
     await msg.reply_text("Session added. ✓")
