import os
import sys 
import math
import time
import asyncio 
import logging
from .utils import STS
from database import db 
from .test import CLIENT , start_clone_bot
from config import Config, temp
from translation import Translation
from pyrogram import Client, filters 
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait, MessageNotModified, RPCError
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, Message 

CLIENT = CLIENT()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

@Client.on_callback_query(filters.regex(r'^start_public'))
async def pub_(bot, message):
    user = message.from_user.id
    temp.CANCEL[user] = False
    frwd_id = message.data.split("_")[2]
    
    if temp.lock.get(user):
        return await message.answer("A previous task is still running.", show_alert=True)
    
    sts = STS(frwd_id)
    if not sts.verify():
        await message.answer("This is an old button. Please start over.", show_alert=True)
        return await message.message.delete()
    
    i = sts.get(full=True)
    if i.TO in temp.IS_FRWD_CHAT:
        return await message.answer("A task is already running for this chat.", show_alert=True)
    
    m = await msg_edit(message.message, "`Verifying...`")
    
    bot_id = temp.FORWARD_BOT_ID.get(user)
    _bot, caption, forward_tag, data, protect, button = await sts.get_data(user, bot_id)

    if not _bot:
        return await msg_edit(m, "No bot or userbot found. Add one in /settings.", wait=True)
    
    temp.lock[user] = True
    
    try:
      client = await start_clone_bot(CLIENT.client(_bot))
    except Exception as e:  
      temp.lock[user] = False
      return await m.edit(f"Failed to start client: {e}")

    try:
        await msg_edit(m, "`Processing...`")
        try: 
            await client.get_chat(i.FROM)
        except Exception as e:
            return await msg_edit(m, f"Source chat is private or invalid. Error: {e}", retry_btn(frwd_id), True)
        
        try:
            k = await client.send_message(i.TO, "Test...")
            await k.delete()
        except Exception as e:
            return await msg_edit(m, f"Bot/userbot must be an admin in the target channel. Error: {e}", retry_btn(frwd_id), True)
        
        temp.forwardings += 1
        await db.add_frwd(user)
        await send(client, user, "Forwarding started...")
        sts.add(time=True)
        sleep = 1 if _bot['is_bot'] else 10
        await msg_edit(m, "`Processing...`") 
        temp.IS_FRWD_CHAT.append(i.TO)

        try:
            MSG = []
            pling = 0
            await edit(m, 'Progressing', 10, sts)

            # Use the patched iter_messages
            async for message in client.iter_messages(chat_id=i.FROM, limit=i.limit, offset=i.skip):
                if await is_cancelled(client, user, m, sts):
                   return
                
                if pling % 20 == 0: 
                   await edit(m, 'Progressing', 10, sts)
                pling += 1
                sts.add('fetched')

                if message.empty or message.service:
                   sts.add('deleted')
                   continue
                
                if forward_tag:
                   MSG.append(message.id)
                   if len(MSG) >= 100: 
                      await forward(client, MSG, m, sts, protect)
                      sts.add('total_files', len(MSG))
                      await asyncio.sleep(10)
                      MSG = []
                else:
                   new_caption = custom_caption(message, caption)
                   details = {"msg_id": message.id, "media": media(message), "caption": new_caption, 'button': button, "protect": protect}
                   await copy(client, details, m, sts)
                   sts.add('total_files')
                   await asyncio.sleep(sleep)
            
            if forward_tag and MSG:
                await forward(client, MSG, m, sts, protect)
                sts.add('total_files', len(MSG))

        except Exception as e:
            await msg_edit(m, f'<b>Error:</b>\n<code>{e}</code>', wait=True)
        
        await send(client, user, "Forwarding complete. ✓")
        await edit(m, 'Completed', "completed", sts)

    finally:
        if i.TO in temp.IS_FRWD_CHAT:
            temp.IS_FRWD_CHAT.remove(i.TO)
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
     await edit(m, 'Progressing', e.value, sts)
     await asyncio.sleep(e.value)
     await edit(m, 'Progressing', 10, sts)
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
     await edit(m, 'Progressing', e.value, sts)
     await asyncio.sleep(e.value)
     await edit(m, 'Progressing', 10, sts)
     await forward(bot, msg, m, sts, protect)

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
   status = 'Forwarding' if status == 10 else f"Sleeping {status}s" if str(status).isnumeric() else status
   percentage = "{:.0f}".format(float(i.fetched)*100/float(i.total)) if i.total > 0 else "0"
   
   now = time.time()
   diff = int(now - i.start) if i.start > 0 else 1
   speed = sts.divide(i.fetched, diff)
   progress = "▰{0}{1}".format(
       ''.join(["▰" for _ in range(math.floor(int(percentage) / 10))]),
       ''.join(["▱" for _ in range(10 - math.floor(int(percentage) / 10))]))
   
   text = Translation.TEXT.format(
        fetched=i.fetched,
        forwarded=i.total_files,
        duplicate=i.duplicate,
        deleted=i.deleted,
        skipped=i.skip,
        filtered=i.filtered,
        status=status,
        percentage=percentage,
        progress_bar=progress
    )

   button = None
   if status not in ["cancelled", "completed"]:
      button = InlineKeyboardMarkup([[InlineKeyboardButton('« Cancel', 'terminate_frwd')]])

   await msg_edit(msg, text, button)
   
async def is_cancelled(client, user, msg, sts):
   if temp.CANCEL.get(user)==True:
      if sts.TO in temp.IS_FRWD_CHAT:
          temp.IS_FRWD_CHAT.remove(sts.TO)
      await edit(msg, "Cancelled", "completed", sts)
      await send(client, user, "Forwarding process cancelled. ❌")
      await stop(client, user)
      return True 
   return False 

async def stop(client, user):
   try:
     await client.stop()
   except:
     pass 
   await db.rmve_frwd(user)
   if temp.forwardings > 0:
       temp.forwardings -= 1
   temp.lock[user] = False 
    
async def send(bot, user, text):
   try:
      await bot.send_message(user, text=text)
   except:
      pass 
     
def custom_caption(msg, caption):
  if not caption or not msg.media:
    return getattr(msg, 'caption', '') or ''
  
  media = getattr(msg, msg.media.value, None)
  if not media:
    return getattr(msg, 'caption', '') or ''

  file_name = getattr(media, 'file_name', '')
  file_size = get_size(getattr(media, 'file_size', 0))
  fcaption = getattr(msg, 'caption', '')
  if fcaption:
      fcaption = fcaption.html
  
  return caption.format(filename=file_name, size=file_size, caption=fcaption)

def get_size(size):
  try:
    units = ["Bytes", "KB", "MB", "GB", "TB", "PB", "EB"]
    size = float(size)
    i = 0
    while size >= 1024.0 and i < len(units):
        i += 1
        size /= 1024.0
    return "%.2f %s" % (size, units[i])
  except:
    return "N/A"

def media(msg):
  if msg.media:
     media = getattr(msg, msg.media.value, None)
     if media:
        return getattr(media, 'file_id', None)
  return None 

def retry_btn(id):
    return InlineKeyboardMarkup([[InlineKeyboardButton('Retry', f"start_public_{id}")]])

@Client.on_callback_query(filters.regex(r'^terminate_frwd$'))
async def terminate_frwding(bot, m):
    user_id = m.from_user.id 
    temp.lock[user_id] = False
    temp.CANCEL[user_id] = True 
    await m.answer("Cancelling...", show_alert=True)
                  
@Client.on_callback_query(filters.regex(r'^close_btn$'))
async def close(bot, update):
    await update.answer()
    await update.message.delete()
    try:
        await update.message.reply_to_message.delete()
    except:
        pass
