import re
import asyncio
import logging
import math
import time
from .utils import STS
from database import db
from .test import CLIENT, start_clone_bot
from config import Config, temp
from translation import Translation
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait, MessageNotModified, RPCError, MediaEmpty
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, Message

CLIENT = CLIENT()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# --- Main Task Starter (Simplified, mr-syd Architecture) ---
@Client.on_callback_query(filters.regex(r'^start_public'))
async def pub_(bot, cb):
    user_id = cb.from_user.id
    if temp.lock.get(user_id):
        return await cb.answer("Please wait for the previous task to complete!", show_alert=True)

    frwd_id = cb.data.split("_")[2]
    temp.CANCEL[frwd_id] = False
    sts = STS(frwd_id)
    if not sts.verify():
        return await cb.answer("This is an old button, please start over.", show_alert=True)

    i = sts.get(full=True)
    m = await msg_edit(cb.message, "Verifying...")

    _bot, caption, forward_tag, data_params, protect, button = await sts.get_data(user_id)
    if not _bot:
        return await msg_edit(m, "You haven't added a bot/userbot. Please do so in /settings.", wait=True)

    delay = data_params.get('forward_delay', 0.5)

    await msg_edit(m, "Starting client...")
    try:
        client = await start_clone_bot(CLIENT.client(_bot), _bot)
    except Exception as e:
        return await m.edit(f"Failed to start client: {e}")

    await msg_edit(m, "Accessing channels...")
    try:
        from_chat_details, to_chat_details = await client.get_chat(i.FROM), await client.get_chat(i.TO)
        from_title, to_title = from_chat_details.title, to_chat_details.title
    except Exception as e:
        await msg_edit(m, f"Error accessing source/target chat: {e}\n\nMake sure your bot/userbot has access.", retry_btn(frwd_id), True)
        return await stop(client, user_id, frwd_id, m)

    if user_id not in temp.ACTIVE_TASKS: temp.ACTIVE_TASKS[user_id] = {}
    temp.ACTIVE_TASKS[user_id][frwd_id] = { "process": m, "details": {"type": "Forwarding", "from": from_title, "to": to_title} }
    temp.lock[user_id] = True
    temp.forwardings += 1
    
    final_status = "error"
    forward_batch = [] # For batching messages when using forward_tag

    try:
        await edit_progress(m, sts, "running")
        
        order_asc = i.start_id < i.end_id
        
        message_iterator = client.iter_messages(
            chat_id=i.FROM,
            reverse=order_asc 
        )

        async for message in message_iterator:
            if temp.CANCEL.get(frwd_id):
                final_status = "cancelled"
                break
            
            if not (min(i.start_id, i.end_id) <= message.id <= max(i.start_id, i.end_id)):
                continue

            sts.add('fetched')
            
            if sts.get('fetched') % 20 == 0:
                await edit_progress(m, sts, "running")

            if not message or message.empty or message.service:
                sts.add('deleted')
                continue

            try:
                if forward_tag:
                    forward_batch.append(message.id)
                    if len(forward_batch) >= 100:
                        await client.forward_messages(
                            chat_id=i.TO, from_chat_id=i.FROM,
                            message_ids=forward_batch, protect_content=protect
                        )
                        sts.add('total_files', len(forward_batch))
                        forward_batch.clear()
                        await asyncio.sleep(max(delay, 2)) # Higher delay for batches
                else:
                    new_caption = custom_caption(message, caption)
                    await message.copy(
                        chat_id=i.TO, caption=new_caption,
                        reply_markup=button, protect_content=protect
                    )
                    sts.add('total_files')
            except FloodWait as e:
                sts.set_status(f"floodwait ({e.value}s)")
                await edit_progress(m, sts, sts.get('status'))
                await asyncio.sleep(e.value + 2)
                sts.set_status("running")
                try:
                    # Retry logic
                    if forward_tag: 
                        # This logic is complex to retry batches, so we skip retry for batches for stability.
                        sts.add('failed', len(forward_batch))
                        forward_batch.clear()
                    else: 
                        await message.copy(chat_id=i.TO, caption=new_caption, reply_markup=button, protect_content=protect)
                        sts.add('total_files')
                except Exception as e_retry:
                    logger.error(f"Retry failed for message {message.id}: {e_retry}")
                    sts.add('failed')
            except Exception as e:
                logger.error(f"Failed to process message {message.id}: {e}", exc_info=False)
                sts.add('failed')

            if not forward_tag:
                await asyncio.sleep(delay)
        
        # Forward any remaining messages in the batch after the loop
        if forward_tag and forward_batch and not temp.CANCEL.get(frwd_id):
            await client.forward_messages(
                chat_id=i.TO, from_chat_id=i.FROM,
                message_ids=forward_batch, protect_content=protect
            )
            sts.add('total_files', len(forward_batch))

        if not temp.CANCEL.get(frwd_id):
            final_status = "completed"

    except Exception as e:
        logger.error(f"Main forwarding loop error: {e}", exc_info=True)
    finally:
        await edit_progress(m, sts, final_status)
        await stop(client, user_id, frwd_id, m)


# --- Callbacks ---
@Client.on_callback_query(filters.regex(r'^frwd_status_'))
async def get_frwd_status(bot, query):
    task_id = query.data.split("_", 2)[2]
    sts = STS(task_id)
    if not sts.verify(): return await query.answer("This task has completed or been cancelled.", show_alert=True)

    i = sts.get(full=True)
    diff = time.time() - i.start
    if diff == 0: diff = 1

    speed = i.fetched / diff
    eta = sts.get_readable_time(int((i.total - i.fetched) / speed if speed > 0 else 0))
    percentage = "{:.2f}".format(i.fetched * 100 / i.total if i.total > 0 else 0.00)

    await query.answer(
        Translation.STATUS_ALERT.format(
            status=i.status, fetched=i.fetched, total=i.total, forwarded=i.total_files,
            failed=i.failed, remaining=(i.total - i.fetched), skipped=i.deleted + i.filtered,
            percentage=percentage, eta=eta
        ),
        show_alert=True
    )

# --- Helper functions ---
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
        return msg

async def edit_progress(msg, sts, status):
    i = sts.get(full=True)
    sts.set_status(status)

    button = None
    if status not in ["cancelled", "completed", "error"]:
        diff = time.time() - i.start
        if diff == 0: diff = 1

        eta = sts.get_readable_time(int((i.total - i.fetched) / (i.fetched / diff) if (i.fetched / diff) > 0 else 0))
        percentage = "{:.2f}".format(i.fetched * 100 / i.total if i.total > 0 else 0.00)
        progress_bar = "▰{0}▱{1}".format('▰' * math.floor(float(percentage) / 10), '▱' * (10 - math.floor(float(percentage) / 10)))

        text = Translation.TEXT.format(
            status=status, fetched=i.fetched, total=i.total, forwarded=i.total_files,
            failed=i.failed, skipped=i.deleted, duplicates=i.duplicate,
            percentage=percentage, eta=eta, progress_bar=progress_bar
        )
        button = InlineKeyboardMarkup([[InlineKeyboardButton(f"📊 Status: {percentage}%", callback_data=f'frwd_status_{i.id}')], [InlineKeyboardButton('❌ Cancel ❌', f'cancel_task_{i.id}')]])
    else:
        text = f"✅ **Task Completed!**\n\n**Processed:** `{i.fetched}`\n**Forwarded:** `{i.total_files}`\n**Failed:** `{i.failed}`"
        if status == "cancelled":
            text = f"❌ **Task Cancelled!**\n\n**Processed:** `{i.fetched}`\n**Forwarded:** `{i.total_files}`\n**Failed:** `{i.failed}`"
        elif status == "error":
            text = f"⚠️ **Error!**\n\nAn unexpected error occurred. Check logs.\n**Processed:** `{i.fetched}`"
        button = InlineKeyboardMarkup([[InlineKeyboardButton("Done!", callback_data="close_btn")]])

    await msg_edit(msg, text, button)

async def stop(client, user_id, task_id, message_obj):
    try: await client.stop()
    except: pass
    if temp.ACTIVE_TASKS.get(user_id, {}).get(task_id): del temp.ACTIVE_TASKS[user_id][task_id]
    temp.CANCEL.pop(task_id, None)
    await db.rmve_frwd(user_id)
    if temp.forwardings > 0: temp.forwardings -= 1
    temp.lock.pop(user_id, None)

def custom_caption(msg, caption):
    if not msg: return ""
    
    fcaption_text = ""
    if msg.text:
        fcaption_text = msg.text.html
    elif msg.caption:
        fcaption_text = msg.caption.html
    
    if not caption: return fcaption_text
    
    file_name, file_size = "", "0 B"
    if msg.media:
        media = getattr(msg, msg.media.value, None)
        if media:
            file_name = getattr(media, 'file_name', '')
            file_size = get_size(getattr(media, 'file_size', 0))
    
    return caption.format(filename=file_name, size=file_size, caption=fcaption_text)

def get_size(size):
    try:
        if not size: return "0 B"
        units, size = ["B", "KB", "MB", "GB", "TB"], float(size)
        i = 0
        while size >= 1024.0 and i < len(units) - 1:
            i += 1
            size /= 1024.0
        return f"{size:.2f} {units[i]}"
    except: return "N/A"

def retry_btn(id):
    return InlineKeyboardMarkup([[InlineKeyboardButton('Retry', f"start_public_{id}")]])
