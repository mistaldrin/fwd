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
from pyrogram.errors import FloodWait, MessageNotModified, RPCError
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, Message

CLIENT = CLIENT()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

CONCURRENCY_LIMIT = 5 # Number of concurrent tasks

# --- Asynchronous Message Generator ---
async def message_generator(client, chat_id, start_id, end_id, is_bot):
    """
    Yields messages from a specific range, handling both bot and userbot clients.
    """
    current_id = min(start_id, end_id)
    target_id = max(start_id, end_id)

    if is_bot:
        # Bots can fetch specific message ID ranges in chunks
        while current_id <= target_id:
            chunk_size = min(100, target_id - current_id + 1)
            message_ids = list(range(current_id, current_id + chunk_size))
            if not message_ids:
                break
            
            messages = await client.get_messages(chat_id, message_ids)
            for message in messages:
                if message: # Filter out empty messages from get_messages
                    yield message
            
            current_id += chunk_size
    else:
        # Userbots should iterate history to be more efficient and avoid bans
        async for message in client.get_chat_history(chat_id):
            if message.id > target_id:
                continue
            if message.id < current_id:
                break
            yield message

# --- Concurrent Worker Function ---
async def process_message_concurrently(
    client, message, sts, caption, forward_tag,
    protect, button, semaphore, frwd_id,
    progress_lock, status_message, delay
):
    """
    Processes a single message within a concurrent environment.
    """
    async with semaphore:
        if temp.CANCEL.get(frwd_id):
            return

        sts.add('fetched')

        if not message or message.empty or message.service:
            sts.add('deleted')
        else:
            if forward_tag:
                sts.add_to_batch(message.id)
            else:
                new_caption = custom_caption(message, caption)
                details = {
                    "msg_id": message.id, "media": media(message), "caption": new_caption,
                    'button': button, "protect": protect,
                    "text": message.text.html if message.text else None
                }
                await copy(client, details, status_message, sts)
                sts.add('total_files')

        # Locked progress update
        async with progress_lock:
            if sts.get('fetched') % 20 == 0 or sts.get('fetched') == sts.get('total'):
                await edit_progress(status_message, sts, "running")
        
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
        from_chat_details = await client.get_chat(i.FROM)
        to_chat_details = await client.get_chat(i.TO)
        from_title, to_title = from_chat_details.title, to_chat_details.title
    except Exception as e:
        await msg_edit(m, f"Error accessing source/target chat: {e}\n\nMake sure your bot/userbot has access and is an admin in the target chat.", retry_btn(frwd_id), True)
        return await stop(client, user_id, frwd_id, m)

    if user_id not in temp.ACTIVE_TASKS:
        temp.ACTIVE_TASKS[user_id] = {}
    temp.ACTIVE_TASKS[user_id][frwd_id] = {
        "process": m,
        "details": {"type": "Forwarding", "from": from_title, "to": to_title}
    }
    temp.lock[user_id] = True
    temp.forwardings += 1

    try:
        await edit_progress(m, sts, "running")
        
        semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
        progress_lock = asyncio.Lock()
        tasks = []

        # Use the message generator
        is_bot_client = _bot.get('is_bot', False)
        message_gen = message_generator(client, i.FROM, i.start_id, i.end_id, is_bot_client)

        async for message in message_gen:
            if temp.CANCEL.get(frwd_id):
                break
            task = asyncio.create_task(
                process_message_concurrently(
                    client, message, sts, caption, forward_tag,
                    protect, button, semaphore, frwd_id,
                    progress_lock, m, delay
                )
            )
            tasks.append(task)
        
        # Wait for all concurrent tasks to complete
        await asyncio.gather(*tasks)

        # Forward any remaining messages in the batch
        if forward_tag and sts.get_batch():
            await forward(client, sts.get_batch(), m, sts, protect)
            sts.add('total_files', len(sts.get_batch()))
            sts.clear_batch()

        final_status = "cancelled" if temp.CANCEL.get(frwd_id) else "completed"
        await edit_progress(m, sts, final_status)

    except Exception as e:
        logger.error(f"Forwarding error: {e}", exc_info=True)
        await msg_edit(m, f'<b>An error occurred:</b>\n<code>{e}</code>', wait=True)
    finally:
        await stop(client, user_id, frwd_id, m)


# --- Callbacks ---
@Client.on_callback_query(filters.regex(r'^frwd_status_'))
async def get_frwd_status(bot, query):
    task_id = query.data.split("_", 2)[2]
    sts = STS(task_id)
    if not sts.verify():
        return await query.answer("This task has completed or been cancelled.", show_alert=True)

    i = sts.get(full=True)
    now = time.time()
    diff = now - i.start
    if diff == 0: diff = 1

    speed = i.fetched / diff
    eta_seconds = (i.total - i.fetched) / speed if speed > 0 else 0
    eta = sts.get_readable_time(int(eta_seconds))
    percentage = "{:.2f}".format(i.fetched * 100 / i.total) if i.total > 0 else "0.00"

    status_text = Translation.STATUS_ALERT.format(
        status=i.status,
        fetched=i.fetched, total=i.total,
        forwarded=i.total_files,
        remaining=(i.total - i.fetched),
        skipped=i.deleted + i.filtered,
        percentage=percentage, eta=eta
    )
    await query.answer(status_text, show_alert=True)


# --- Helper functions ---
async def copy(bot, msg, m, sts):
    try:
        if msg.get("media"):
            await bot.copy_message(
                chat_id=sts.get('TO'), from_chat_id=sts.get('FROM'),
                message_id=msg.get("msg_id"), caption=msg.get("caption"),
                reply_markup=msg.get('button'), protect_content=msg.get("protect", False))
        elif msg.get("text"):
            await bot.send_message(
                chat_id=sts.get('TO'), text=msg.get("text"),
                reply_markup=msg.get('button'), protect_content=msg.get("protect", False))
        else:
            sts.add('deleted')
    except FloodWait as e:
        await edit_progress(m, sts, f"floodwait ({e.value}s)")
        await asyncio.sleep(e.value + 2) # Add buffer
        await copy(bot, msg, m, sts) # Retry
    except Exception as e:
        logger.warning(f"Failed to copy message {msg.get('msg_id')}: {e}")
        sts.add('deleted')

async def forward(bot, msg_ids, m, sts, protect):
    try:
        await bot.forward_messages(
            chat_id=sts.get('TO'), from_chat_id=sts.get('FROM'),
            protect_content=protect, message_ids=msg_ids)
    except FloodWait as e:
        await edit_progress(m, sts, f"floodwait ({e.value}s)")
        await asyncio.sleep(e.value + 2) # Add buffer
        await forward(bot, msg_ids, m, sts, protect) # Retry

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
    if status not in ["cancelled", "completed"]:
        now = time.time()
        diff = now - i.start
        if diff == 0: diff = 1

        speed = i.fetched / diff
        eta_seconds = (i.total - i.fetched) / speed if speed > 0 else 0
        eta = sts.get_readable_time(int(eta_seconds))
        percentage = "{:.2f}".format(i.fetched * 100 / i.total) if i.total > 0 else "0.00"

        progress_bar = "▰{0}▱{1}".format(
            '▰' * math.floor(float(percentage) / 10),
            '▱' * (10 - math.floor(float(percentage) / 10))
        )

        text = Translation.TEXT.format(
            fetched=i.fetched, total=i.total, forwarded=i.total_files,
            skipped=i.deleted, duplicates=i.duplicate,
            status=status, percentage=percentage, eta=eta, progress_bar=progress_bar
        )

        button = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"📊 Status: {percentage}%", callback_data=f'frwd_status_{i.id}')],
            [InlineKeyboardButton('❌ Cancel ❌', f'cancel_task_{i.id}')]
        ])
    else:
        final_text = f"✅ **Task Completed!**\n\n**Processed:** `{i.fetched}`\n**Forwarded:** `{i.total_files}`"
        if status == "cancelled":
            final_text = f"❌ **Task Cancelled!**\n\n**Processed:** `{i.fetched}`\n**Forwarded:** `{i.total_files}`"
        text = final_text
        button = InlineKeyboardMarkup([[InlineKeyboardButton("Done!", callback_data="close_btn")]])

    await msg_edit(msg, text, button)

async def stop(client, user_id, task_id, message_obj):
    try:
        await client.stop()
    except: pass

    if temp.ACTIVE_TASKS.get(user_id, {}).get(task_id):
        del temp.ACTIVE_TASKS[user_id][task_id]

    temp.CANCEL.pop(task_id, None)
    await db.rmve_frwd(user_id)
    if temp.forwardings > 0:
        temp.forwardings -= 1
    temp.lock.pop(user_id, None)

def custom_caption(msg, caption):
    if not msg: return ""
    if not msg.media and not caption:
        return (msg.text or "").html if msg.text else ""
    if not msg.media and caption:
        return caption.format(filename="", size="", caption=(msg.text or "").html)

    media = getattr(msg, msg.media.value, None) if msg.media else None
    if not media:
        return (msg.caption or "").html if msg.caption else ""

    file_name = getattr(media, 'file_name', '')
    file_size = get_size(getattr(media, 'file_size', 0))
    fcaption = (msg.caption or "").html if msg.caption else ""

    if caption:
        return caption.format(filename=file_name, size=file_size, caption=fcaption)
    return fcaption

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
    if msg and msg.media and hasattr(msg, 'media') and hasattr(msg, 'media', 'value'):
        media_obj = getattr(msg, msg.media.value, None)
        if media_obj:
            return getattr(media_obj, 'file_id', None)
    return None

def retry_btn(id):
    return InlineKeyboardMarkup([[InlineKeyboardButton('Retry', f"start_public_{id}")]])
