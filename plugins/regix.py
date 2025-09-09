# mistaldrin/fwd/fwd-dawn-improve-v2/plugins/regix.py
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

CONCURRENCY_LIMIT = 5 # Number of concurrent tasks

# --- Asynchronous Message Generator ---
async def message_generator(client, chat_id, start_id, end_id, is_bot, order_asc):
    """
    Yields messages from a specific range, handling both bot and userbot clients and order.
    """
    if is_bot:
        message_ids = list(range(start_id, end_id + 1))
        if not order_asc: message_ids.reverse()
        
        for i in range(0, len(message_ids), 100):
            chunk = message_ids[i:i+100]
            if not chunk: break
            
            try:
                messages = await client.get_messages(chat_id, chunk)
                for message in messages:
                    if message: yield message
            except Exception as e:
                logger.error(f"Error fetching message chunk for bot: {e}")
    else:
        try:
            async for message in client.get_chat_history(chat_id):
                if message.id > max(start_id, end_id): continue
                if message.id < min(start_id, end_id): break
                yield message
        except Exception as e:
            logger.error(f"Error fetching chat history for userbot: {e}")

# --- Dedicated Progress Updater ---
async def progress_updater(status_message, sts, all_tasks):
    """
    Updates the progress message at regular intervals until all tasks are complete.
    """
    while not all(t.done() for t in all_tasks):
        try:
            await edit_progress(status_message, sts, sts.get('status'))
        except Exception as e:
            logger.warning(f"Progress updater error: {e}")
        await asyncio.sleep(10)

# --- Resilient Concurrent Worker Function ---
async def process_message_concurrently(
    client, message, sts, caption, forward_tag,
    protect, button, semaphore, frwd_id, delay, flood_wait_event
):
    """
    Processes a single message within a concurrent environment with robust error handling.
    """
    async with semaphore:
        await flood_wait_event.wait() # Wait if a floodwait is active
        if temp.CANCEL.get(frwd_id):
            return

        try:
            sts.add('fetched')
            if not message or message.empty or message.service:
                sts.add('deleted')
            else:
                if forward_tag:
                    sts.add_to_batch(message.id)
                    sts.add('total_files')
                else:
                    new_caption = custom_caption(message, caption)
                    await client.copy_message(
                        chat_id=sts.get('TO'), from_chat_id=sts.get('FROM'),
                        message_id=message.id, caption=new_caption,
                        reply_markup=button, protect_content=protect
                    )
                    sts.add('total_files')
        except FloodWait as e:
            sts.set_status(f"floodwait ({e.value}s)")
            flood_wait_event.clear() # PAUSE all other tasks
            await asyncio.sleep(e.value + 2)
            flood_wait_event.set() # RESUME all other tasks
            sts.set_status("running")
            # Re-add the task to be processed again
            await process_message_concurrently(client, message, sts, caption, forward_tag, protect, button, semaphore, frwd_id, delay, flood_wait_event)
            return # Exit current attempt
        except (MediaEmpty, RPCError) as e:
            logger.warning(f"Skipping message {message.id} due to RPC/Media Error: {e}")
            sts.add('failed')
        except Exception as e:
            logger.error(f"FATAL: Failed to process message {message.id}: {e}", exc_info=True)
            sts.add('failed')
        
        await asyncio.sleep(delay)

# --- Main Task Starter ---
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

    updater_task = None
    try:
        await edit_progress(m, sts, "running")
        
        semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
        tasks = []
        flood_wait_event = asyncio.Event()
        flood_wait_event.set() # Initially set to allow tasks to run

        is_bot_client = _bot.get('is_bot', False)
        order_asc = i.start_id < i.end_id
        message_gen = message_generator(client, i.FROM, min(i.start_id, i.end_id), max(i.start_id, i.end_id), is_bot_client, order_asc)

        async for message in message_gen:
            if temp.CANCEL.get(frwd_id): break
            task = asyncio.create_task(process_message_concurrently(client, message, sts, caption, forward_tag, protect, button, semaphore, frwd_id, delay, flood_wait_event))
            tasks.append(task)
        
        updater_task = asyncio.create_task(progress_updater(m, sts, tasks))

        await asyncio.gather(*tasks)

        if forward_tag and sts.get_batch():
            for i in range(0, len(sts.get_batch()), 100):
                await forward(client, sts.get_batch()[i:i+100], m, sts, protect, flood_wait_event)

        final_status = "cancelled" if temp.CANCEL.get(frwd_id) else "completed"
        
    except Exception as e:
        logger.error(f"Main forwarding loop error: {e}", exc_info=True)
        final_status = "error"
    finally:
        if updater_task and not updater_task.done():
            updater_task.cancel()
        # Final progress update
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
async def forward(bot, msg_ids, m, sts, protect, flood_wait_event):
    try:
        await flood_wait_event.wait()
        await bot.forward_messages(chat_id=sts.get('TO'), from_chat_id=sts.get('FROM'), protect_content=protect, message_ids=msg_ids)
    except FloodWait as e:
        sts.set_status(f"floodwait ({e.value}s)")
        flood_wait_event.clear()
        await asyncio.sleep(e.value + 2)
        flood_wait_event.set()
        sts.set_status("running")
        await forward(bot, msg_ids, m, sts, protect, flood_wait_event)

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
            text = f"⚠️ **Error!**\n\nAn unexpected error occurred. Please check the logs.\n**Processed:** `{i.fetched}`"
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
    fcaption = (msg.caption or "").html if msg.caption else ""
    if not caption: return fcaption
    
    file_name, file_size = "", "0 B"
    if msg.media:
        media = getattr(msg, msg.media.value, None)
        if media:
            file_name = getattr(media, 'file_name', '')
            file_size = get_size(getattr(media, 'file_size', 0))
    
    return caption.format(filename=file_name, size=file_size, caption=fcaption)

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
