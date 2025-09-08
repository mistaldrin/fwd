import os
import sys 
import math
import time
import asyncio 
import logging
from .utils import STS
from database import db 
from .test import CLIENT, start_clone_bot
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
async def pub_(bot, cb):
    user_id = cb.from_user.id
    if temp.lock.get(user_id):
      return await cb.answer("Please wait for the previous task to complete!", show_alert=True)
    
    frwd_id = cb.data.split("_")[2]
    temp.CANCEL[frwd_id] = False # Use unique task ID for cancellation
    sts = STS(frwd_id)
    if not sts.verify():
      return await cb.answer("This is an old button, please start over.", show_alert=True)

    i = sts.get(full=True)
    
    # Initial verification message
    m = await msg_edit(cb.message, "Verifying...")
    
    _bot, caption, forward_tag, data_params, protect, button = await sts.get_data(user_id)
    
    if not _bot:
      return await msg_edit(m, "You haven't added a bot/userbot. Please do so in /settings.", wait=True)

    try:
      client = await start_clone_bot(CLIENT.client(_bot))
    except Exception as e:  
      return await m.edit(f"Failed to start client: {e}")

    # Verify access to source and target chats
    try: 
       from_chat_details = await client.get_chat(i.FROM)
       to_chat_details = await client.get_chat(i.TO)
       from_title = from_chat_details.title
       to_title = to_chat_details.title
    except Exception as e:
       await msg_edit(m, f"Error accessing source/target chat: {e}\n\nMake sure your bot/userbot has access and is an admin in the target chat.", retry_btn(frwd_id), True)
       return await stop(client, user_id, frwd_id, m) # Pass message obj for cleanup
    
    # --- Register the task ---
    if user_id not in temp.ACTIVE_TASKS:
        temp.ACTIVE_TASKS[user_id] = {}
    temp.ACTIVE_TASKS[user_id][frwd_id] = {
        "process": m,
        "details": {"type": "Forwarding", "from": from_title, "to": to_title}
    }

    temp.lock[user_id] = True
    temp.forwardings += 1
    await db.add_frwd(user_id)
    await send(bot, user_id, "Forwarding Started!")
    sts.add(time=True)
    sleep_duration = data_params.get('forward_delay', 1.0)
    
    try:
        # --- Main Processing Loop ---
        messages_to_process = []
        start_point = max(i.start_id, i.end_id)
        end_point = min(i.start_id, i.end_id)
        
        async for message in client.get_chat_history(chat_id=i.FROM):
            if message.id > start_point: continue
            if message.id < end_point: break
            messages_to_process.append(message)

        if i.start_id < i.end_id:
            messages_to_process.reverse()
        # --- End of message fetching ---
        
        MSG_batch = []
        
        for message in messages_to_process:
            if temp.CANCEL.get(frwd_id):
                await is_cancelled(client, user_id, m, sts, frwd_id)
                return

            sts.add('fetched')
            
            if message.empty or message.service:
               sts.add('deleted')
               continue

            if forward_tag:
               MSG_batch.append(message.id)
               if len(MSG_batch) >= 100 or (sts.fetched == i.total):
                  await forward(client, MSG_batch, m, sts, protect)
                  sts.add('total_files', len(MSG_batch))
                  await asyncio.sleep(10)
                  MSG_batch = []
            else:
               new_caption = custom_caption(message, caption)
               details = {"msg_id": message.id, "media": media(message), "caption": new_caption, 'button': button, "protect": protect, "text": message.text.html if message.text else None}
               await copy(client, details, m, sts)
               sts.add('total_files')
               await asyncio.sleep(sleep_duration)
            
            # Update progress every 20 messages
            if sts.fetched % 20 == 0:
                await edit_progress(m, sts, "running")

        if forward_tag and MSG_batch:
            await forward(client, MSG_batch, m, sts, protect)
            sts.add('total_files', len(MSG_batch))

        await send(bot, user_id, "Forwarding Completed!")
        await edit_progress(m, sts, "completed") 
    
    except Exception as e:
        logger.error(f"Forwarding error: {e}", exc_info=True)
        await msg_edit(m, f'<b>An error occurred:</b>\n<code>{e}</code>', wait=True)
    
    finally:
        await stop(client, user_id, frwd_id, m)


# --- Helper functions ---
async def copy(bot, msg, m, sts):
   try:
     if msg.get("media"):
        await bot.copy_message(
              chat_id=sts.get('TO'),
              from_chat_id=sts.get('FROM'),
              message_id=msg.get("msg_id"),
              caption=msg.get("caption"),
              reply_markup=msg.get('button'),
              protect_content=msg.get("protect", False))
     elif msg.get("text"): 
        await bot.send_message(
              chat_id=sts.get('TO'),
              text=msg.get("text"),
              reply_markup=msg.get('button'),
              protect_content=msg.get("protect", False)
        )
     else:
        sts.add('deleted')
   except FloodWait as e:
     await edit_progress(m, sts, f"floodwait ({e.value}s)")
     await asyncio.sleep(e.value)
     await copy(bot, msg, m, sts)
   except Exception as e:
     logger.warning(f"Failed to copy message {msg.get('msg_id')}: {e}")
     sts.add('deleted')
        
async def forward(bot, msg_ids, m, sts, protect):
   try:                             
     await bot.forward_messages(
           chat_id=sts.get('TO'),
           from_chat_id=sts.get('FROM'), 
           protect_content=protect,
           message_ids=msg_ids)
   except FloodWait as e:
     await edit_progress(m, sts, f"floodwait ({e.value}s)")
     await asyncio.sleep(e.value)
     await forward(bot, msg_ids, m, sts, protect)

async def msg_edit(msg, text, button=None, wait=None):
    try:
        return await msg.edit(text, reply_markup=button, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    except MessageNotModified:
        return msg
    except FloodWait as e:
        if wait:
           await asyncio.sleep(e.value)
           return await msg_edit(msg, text, button, wait)
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        return msg


async def edit_progress(msg, sts, status):
    i = sts.get(full=True)
    now = time.time()
    diff = now - i.start
    if diff == 0: diff = 1 # Avoid division by zero
    
    speed = i.fetched / diff
    if speed == 0: speed = 1 # Avoid division by zero
    
    eta_seconds = (i.total - i.fetched) / speed
    eta = sts.get_readable_time(int(eta_seconds))
    
    percentage = "{:.2f}".format(i.fetched * 100 / i.total) if i.total > 0 else "0.00"
    progress = "▰{0}▱".format('▰' * (math.floor(float(percentage) / 10) -1) if float(percentage) > 10 else '')
    
    text = Translation.TEXT.format(
       fetched=i.fetched, total=i.total,
       forwarded=i.total_files, duplicate=i.duplicate,
       deleted=i.deleted + i.filtered, status=status,
       percentage=percentage, progress_bar=progress,
       eta=eta, speed=round(speed, 2)
    )
    
    button = None
    if status not in ["cancelled", "completed"]:
      button = InlineKeyboardMarkup([[InlineKeyboardButton('❌ Cancel Task', f'cancel_task_{i.id}')]])
   
    await msg_edit(msg, text, button)
   
async def is_cancelled(client, user, msg, sts, task_id):
    if temp.CANCEL.get(task_id):
        await edit_progress(msg, sts, "cancelled")
        await send(client, user, "❌ Forwarding Process Cancelled")
        return True
    return False

async def stop(client, user_id, task_id, message_obj):
   try:
     await client.stop()
   except: pass 
   
   # Unregister the task
   if temp.ACTIVE_TASKS.get(user_id, {}).get(task_id):
       del temp.ACTIVE_TASKS[user_id][task_id]

   temp.CANCEL.pop(task_id, None)
   await db.rmve_frwd(user_id)
   if temp.forwardings > 0:
       temp.forwardings -= 1
   temp.lock.pop(user_id, None)
    
async def send(bot, user, text):
   try:
      await bot.send_message(user, text=text)
   except: pass 
     
def custom_caption(msg, caption):
  if not caption or not msg.media:
      return (msg.caption or "").html if msg.caption else ""

  media = getattr(msg, msg.media.value, None)
  if not media:
      return (msg.caption or "").html if msg.caption else ""
      
  file_name = getattr(media, 'file_name', '')
  file_size = get_size(getattr(media, 'file_size', 0))
  fcaption = (msg.caption or "").html if msg.caption else ""
  
  return caption.format(filename=file_name, size=file_size, caption=fcaption)

def get_size(size):
  try:
    if not size: return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(size)
    i = 0
    while size >= 1024.0 and i < len(units) - 1:
        i += 1
        size /= 1024.0
    return f"{size:.2f} {units[i]}"
  except: return "N/A"

def media(msg):
  return getattr(getattr(msg, msg.media.value, None), 'file_id', None)

def retry_btn(id):
    return InlineKeyboardMarkup([[InlineKeyboardButton('Retry', f"start_public_{id}")]])
