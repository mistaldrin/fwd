import os
import asyncio
import io
import random
import time
import math
from uuid import uuid4
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ChatMemberStatus, ParseMode
from pyrogram.errors import FloodWait, ChannelInvalid, UsernameNotOccupied, UsernameInvalid, PeerIdInvalid, UserAlreadyParticipant, MessageNotModified

from .test import CLIENT
from .utils import start_range_selection, get_readable_time
from translation import Translation
from config import temp
from database import db

# --- Constants for the interactive menu ---
OPTION_LABELS = ["Text", "Photos/Videos", "Audio", "Documents", "Stickers"]
DEFAULT_STATE = "01010"
SYD = ["https://files.catbox.moe/3lwlbm.png"]


def create_selection_keyboard(selection_state: str, session_id: str) -> InlineKeyboardMarkup:
    """Creates the interactive keyboard for selecting message types."""
    buttons = []
    state_list = list(selection_state)

    for i, label in enumerate(OPTION_LABELS):
        text = f"✓ {label}" if state_list[i] == '1' else label
        callback_data = f"uneq_toggle_{selection_state}_{i}_{session_id}"
        buttons.append([InlineKeyboardButton(text, callback_data=callback_data)])

    buttons.append([
        InlineKeyboardButton("✓ Start Scan", callback_data=f"uneq_startscan_{selection_state}_{session_id}"),
        InlineKeyboardButton("« Cancel", callback_data=f"range_cancel_{session_id}")
    ])
    return InlineKeyboardMarkup(buttons)

async def prompt_type_selection(bot, query, session_id):
    """Sends the message with the type selection keyboard."""
    keyboard = create_selection_keyboard(DEFAULT_STATE, session_id)
    await bot.send_photo(
        chat_id=query.from_user.id,
        photo=random.choice(SYD),
        caption="<b>Select Message Types</b>\n\nSelect the types of messages to find duplicates of.",
        reply_markup=keyboard
    )

@Client.on_message(filters.command("unequify") & filters.private)
async def unequify_start(bot: Client, message: Message):
    """
    Initial entry point for the /unequify command.
    """
    user_id = message.from_user.id
    if temp.lock.get(user_id):
        return await message.reply("A task is already in progress. Please wait for it to complete.")

    temp.USER_STATES.pop(user_id, None)
    
    ban_status = await db.get_ban_status(user_id)
    if ban_status["is_banned"]:
        return await message.reply_text(f"Access denied.\n\nReason: {ban_status['ban_reason']}")

    userbots = [b for b in await db.get_bots(user_id) if not b.get('is_bot')]
    if not userbots:
        return await message.reply_text("Add a userbot to proceed.\n( >⁠.⁠< ) --> /settings")

    command_args = message.command[1:] if len(message.command) > 1 else []
    temp.USER_STATES[user_id] = {"command_args": command_args}

    if len(userbots) > 1:
        buttons = [[InlineKeyboardButton(ub['name'], callback_data=f"uneq_select_ub_{ub['id']}")] for ub in userbots]
        buttons.append([InlineKeyboardButton("« Cancel", callback_data="close_btn")])
        await message.reply_photo(photo=random.choice(SYD), caption="<b>Select a Userbot</b>", reply_markup=InlineKeyboardMarkup(buttons))
        return

    await process_userbot_selection(bot, message, user_id, userbots[0]['id'])

@Client.on_callback_query(filters.regex("^uneq_select_ub_"))
async def cb_select_userbot_unequify(bot: Client, query: CallbackQuery):
    userbot_id = int(query.data.split('_')[-1])
    await query.message.delete()
    await process_userbot_selection(bot, query.message, query.from_user.id, userbot_id)

async def process_userbot_selection(bot: Client, message: Message, user_id: int, userbot_id: int):
    temp.UNEQUIFY_USERBOT_ID[user_id] = userbot_id
    state_info = temp.USER_STATES.get(user_id, {})
    command_args = state_info.get("command_args", [])

    if command_args:
        target = command_args[0]
        await process_unequify_target(bot, message, user_id, userbot_id, target)
    else:
        await unequify_continue(bot, message, user_id, userbot_id)

async def process_unequify_target(bot: Client, message: Message, user_id: int, userbot_id: int, target_channel_input: str):
    status_msg = await message.reply("`Verifying target channel...`")
    try:
        userbot_config = await db.get_bot(user_id, userbot_id)
        if not userbot_config: 
            return await status_msg.edit("Selected userbot not found.")

        async with CLIENT().client(userbot_config) as temp_client:
            chat = await temp_client.get_chat(target_channel_input)
            last_msg_id = 0
            async for last_message in temp_client.get_chat_history(chat.id, limit=1):
                last_msg_id = last_message.id
                break
            await status_msg.delete()
            await start_range_selection(bot, message, from_chat_id=chat.id, from_title=chat.title, to_chat_id=None, start_id=1, end_id=last_msg_id, final_callback_prefix="uneq_final")
    except (UsernameInvalid, PeerIdInvalid, ChannelInvalid, UsernameNotOccupied) as e:
        await status_msg.edit(f"Could not find the chat: `{e}`. Please check the username/ID and ensure your userbot is a member.")
    except Exception as e:
        await status_msg.edit(f"An error occurred: {e}")


async def unequify_continue(bot: Client, message: Message, user_id: int, userbot_id: int):
    temp.UNEQUIFY_USERBOT_ID[user_id] = userbot_id
    buttons = [
        [InlineKeyboardButton("Manual Input", callback_data="uneq_manual")],
        [InlineKeyboardButton("Select from Userbot Chats", callback_data="uneq_select_from_ub")]
    ]
    await message.reply_photo(photo=random.choice(SYD), caption=Translation.UNEQUIFY_START_TXT, reply_markup=InlineKeyboardMarkup(buttons))


@Client.on_callback_query(filters.regex("^uneq_"))
async def unequify_callbacks(bot: Client, query: CallbackQuery):
    user_id = query.from_user.id
    data = query.data.split("_", 1)[1]
    
    if query.message:
        await query.message.delete()

    if data == "manual":
        temp.USER_STATES[user_id] = {"state": "awaiting_unequify_manual_target"}
        await bot.send_message(user_id, "Send the channel username or ID.")

    elif data == "select_from_ub":
        userbot_id = temp.UNEQUIFY_USERBOT_ID.get(user_id)
        if not userbot_id: return await bot.send_message(user_id, "Error: Bot selection lost. Please start over.")
        
        userbot_config = await db.get_bot(user_id, userbot_id)
        if not userbot_config: return await bot.send_message(user_id, "Userbot not found.")
        
        status_msg = await bot.send_message(user_id, "`⏳ Fetching chats...`")

        chats, serial, text = {}, 1, "Reply with the number or Chat ID of the target channel.\n\n"
        try:
            async with CLIENT().client(userbot_config) as userbot:
                async for dialog in userbot.get_dialogs(limit=50):
                    chats[str(serial)] = dialog.chat
                    chats[str(dialog.chat.id)] = dialog.chat
                    text += f"<b>{serial}.</b> {dialog.chat.title} (<code>{dialog.chat.id}</code>)\n"
                    serial += 1
            
            await status_msg.delete()
            
            prompt_message = await bot.send_message(user_id, text, parse_mode=ParseMode.HTML)
            temp.USER_STATES[user_id] = {
                "state": "awaiting_unequify_chat_selection",
                "chats": chats,
                "prompt_message": prompt_message
            }
        except Exception as e:
            await status_msg.edit(f"An error occurred: `{e}`")

    elif data.startswith("toggle_"):
        _, current_state, index_str, session_id = data.split("_", 3)
        index = int(index_str)
        state_list = list(current_state)
        state_list[index] = '1' if state_list[index] == '0' else '0'
        new_state = "".join(state_list)
        if query.message:
            await query.message.edit_reply_markup(create_selection_keyboard(new_state, session_id))
        await query.answer()

    elif data.startswith("startscan_"):
        _, selection_state, session_id = data.split("_", 2)
        await start_deduplication(bot, query, selection_state, session_id)

@Client.on_callback_query(filters.regex(r'^uneq_status_'))
async def get_uneq_status(bot, query):
    task_id = query.data.split("_", 2)[2]
    task_data = temp.ACTIVE_TASKS.get(query.from_user.id, {}).get(task_id)
    if not task_data:
        return await query.answer("This task has completed or been cancelled.", show_alert=True)
    
    stats = task_data.get("stats", {})
    scanned = stats.get("scanned", 0)
    total = stats.get("total", 0)
    deleted = stats.get("deleted", 0)
    start_time = stats.get("start_time", 0)
    
    now = time.time()
    diff = now - start_time
    if diff == 0: diff = 1
    
    speed = scanned / diff
    eta_seconds = (total - scanned) / speed if speed > 0 else 0
    eta = get_readable_time(int(eta_seconds))
    percentage = "{:.2f}".format(scanned * 100 / total) if total > 0 else "0.00"

    status_text = Translation.STATUS_ALERT.format(
        fetched=scanned, total=total,
        forwarded=deleted, # Using forwarded field for deleted count
        deleted=deleted,
        eta=eta, percentage=percentage
    )
    await query.answer(status_text, show_alert=True)

async def start_deduplication(bot: Client, callback_query: CallbackQuery, selection_state: str, session_id: str):
    user_id = callback_query.from_user.id
    task_id = str(uuid4())
    
    range_session = temp.RANGE_SESSIONS.pop(session_id, None)
    if not range_session:
        return await bot.send_message(user_id, "Error: Session expired or invalid.")

    userbot_id = temp.UNEQUIFY_USERBOT_ID.get(user_id)
    if not userbot_id:
        return await bot.send_message(user_id, "Error: Bot selection lost.")

    userbot_config = await db.get_bot(user_id, userbot_id)
    if not userbot_config:
        return await bot.send_message(user_id, "Error: Userbot not found.")

    target_channel, start_id, end_id = range_session['from_chat_id'], min(range_session['start_id'], range_session['end_id']), max(range_session['start_id'], range_session['end_id'])
    
    status_message = await bot.send_message(user_id, "`Initializing...`")
    
    if user_id not in temp.ACTIVE_TASKS:
        temp.ACTIVE_TASKS[user_id] = {}
    temp.ACTIVE_TASKS[user_id][task_id] = {
        "process": status_message,
        "details": {"type": "Deduplication", "from": range_session['from_title'], "to": "N/A"},
        "stats": {}
    }
    temp.CANCEL[task_id] = False
    temp.lock[user_id] = True

    seen_identifiers, duplicates_to_delete = set(), []
    total_scanned, total_deleted = 0, 0
    total_in_range = abs(end_id - start_id) + 1
    start_time = time.time()
    last_edit_time = time.time()

    try:
        async with CLIENT().client(userbot_config) as userbot:
            message_ids_to_scan = list(range(start_id, end_id + 1))

            for i in range(0, len(message_ids_to_scan), 200):
                if temp.CANCEL.get(task_id):
                    break
                
                chunk = message_ids_to_scan[i:i+200]
                messages = await userbot.get_messages(target_channel, chunk)

                for msg in messages:
                    if not msg: continue
                    total_scanned += 1
                    identifier = None
                    
                    if selection_state[0] == '1' and msg.text: identifier = msg.text.strip()
                    elif selection_state[1] == '1' and (msg.photo or msg.video):
                        media_obj = msg.photo or msg.video
                        if media_obj: identifier = getattr(media_obj, 'file_unique_id', None)
                    elif selection_state[2] == '1' and msg.audio: identifier = msg.audio.file_unique_id
                    elif selection_state[3] == '1' and msg.document: identifier = msg.document.file_unique_id
                    elif selection_state[4] == '1' and msg.sticker: identifier = msg.sticker.file_unique_id

                    if identifier and identifier in seen_identifiers:
                        duplicates_to_delete.append(msg.id)
                    elif identifier:
                        seen_identifiers.add(identifier)

                if len(duplicates_to_delete) >= 100:
                    await userbot.delete_messages(chat_id=target_channel, message_ids=duplicates_to_delete)
                    total_deleted += len(duplicates_to_delete)
                    duplicates_to_delete.clear()
                    await asyncio.sleep(5)

                current_time = time.time()
                if current_time - last_edit_time > 15:
                    await edit_unequify_progress(status_message, total_scanned, total_deleted, total_in_range, start_time, task_id, "running")
                    last_edit_time = current_time

            if duplicates_to_delete and not temp.CANCEL.get(task_id):
                await userbot.delete_messages(chat_id=target_channel, message_ids=duplicates_to_delete)
                total_deleted += len(duplicates_to_delete)
            
            final_status = "cancelled" if temp.CANCEL.get(task_id) else "completed"
            await edit_unequify_progress(status_message, total_scanned, total_deleted, total_in_range, start_time, task_id, final_status)

    except Exception as e:
        await status_message.edit(f"❌ **An unexpected error occurred.**\n\n`{e}`")
    finally:
        if temp.ACTIVE_TASKS.get(user_id, {}).get(task_id):
            del temp.ACTIVE_TASKS[user_id][task_id]
        temp.CANCEL.pop(task_id, None)
        temp.lock.pop(user_id, None)


async def edit_unequify_progress(msg, scanned, deleted, total, start_time, task_id, status):
    temp.ACTIVE_TASKS[msg.chat.id][task_id]["stats"] = {
        "scanned": scanned, "deleted": deleted, "total": total, "start_time": start_time
    }
    
    text = Translation.DUPLICATE_TEXT.format(status=status)
    button = None

    if status not in ["cancelled", "completed"]:
        button = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"📊 Status 📊", callback_data=f'uneq_status_{task_id}')],
            [InlineKeyboardButton('❌ Cancel ❌', f'cancel_task_{task_id}')]
        ])
    else:
        text = f"✅ **Deduplication Completed!**\n\n**Scanned:** `{scanned}`\n**Duplicates Deleted:** `{deleted}`"
        if status == "cancelled":
            text = "❌ **Task Cancelled!**"
            
    try:
        await msg.edit_text(text, reply_markup=button)
    except MessageNotModified:
        pass
    except Exception as e:
        print(f"Error updating unequify progress: {e}")
