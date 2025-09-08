import os
import asyncio
import io
import random
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ChatMemberStatus, ParseMode
from pyrogram.errors import FloodWait, ChannelInvalid, UsernameNotOccupied, UsernameInvalid, PeerIdInvalid, UserAlreadyParticipant

from .test import CLIENT
from .utils import start_range_selection
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
    temp.USER_STATES.pop(user_id, None) # Clear previous states
    
    ban_status = await db.get_ban_status(user_id)
    if ban_status["is_banned"]:
        return await message.reply_text(f"Access denied.\n\nReason: {ban_status['ban_reason']}")

    userbots = [b for b in await db.get_bots(user_id) if not b.get('is_bot')]
    if not userbots:
        return await message.reply_text("Add a userbot to proceed.\n( >⁠.⁠< ) --> /settings")

    if len(userbots) > 1:
        buttons = [[InlineKeyboardButton(ub['name'], callback_data=f"uneq_select_ub_{ub['id']}")] for ub in userbots]
        buttons.append([InlineKeyboardButton("« Cancel", callback_data="close_btn")])
        await message.reply_photo(photo=random.choice(SYD), caption="<b>Select a Userbot</b>", reply_markup=InlineKeyboardMarkup(buttons))
        return
    
    # If there's a target in the command (e.g., /unequify @channel)
    if len(message.command) > 1:
        target = message.command[1]
        await process_unequify_target(bot, message, user_id, userbots[0]['id'], target)
    else:
        await unequify_continue(bot, message, user_id, userbots[0]['id'])


@Client.on_callback_query(filters.regex("^uneq_select_ub_"))
async def cb_select_userbot_unequify(bot: Client, query: CallbackQuery):
    userbot_id = int(query.data.split('_')[-1])
    await query.message.delete()
    
    # Check if original message had a target
    target = None
    original_message = query.message.reply_to_message or query.message
    if len(original_message.command) > 1:
        target = original_message.command[1]
    
    if target:
        await process_unequify_target(bot, original_message, query.from_user.id, userbot_id, target)
    else:
        await unequify_continue(bot, original_message, query.from_user.id, userbot_id)


async def process_unequify_target(bot: Client, message: Message, user_id: int, userbot_id: int, target_channel_input: str):
    """Processes the target channel provided and starts the range selection."""
    try:
        userbot_config = await db.get_bot(user_id, userbot_id)
        if not userbot_config: return await message.reply("Selected userbot not found.")

        async with CLIENT().client(userbot_config) as temp_client:
            chat = await temp_client.get_chat(target_channel_input)
            last_msg_id = 0
            async for last_message in temp_client.get_chat_history(chat.id, limit=1):
                last_msg_id = last_message.id
                break
            await start_range_selection(bot, message, from_chat_id=chat.id, from_title=chat.title, to_chat_id=None, start_id=1, end_id=last_msg_id, final_callback_prefix="uneq_final")
    except (UsernameInvalid, PeerIdInvalid, ChannelInvalid, UsernameNotOccupied) as e:
        await message.reply(f"Could not find the chat: `{e}`. Please check the username/ID and ensure your userbot is a member.")
    except Exception as e:
        await message.reply(f"An error occurred: {e}")


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
    
    await query.message.delete() # Clean up the prompt

    if data == "manual":
        try:
            ask_msg = await bot.ask(user_id, "Send the channel username or ID.", timeout=300)
            target = ask_msg.text
            userbot_id = temp.UNEQUIFY_USERBOT_ID.get(user_id)
            if not userbot_id:
                return await ask_msg.reply("Userbot selection lost. Please start over.")
            await process_unequify_target(bot, ask_msg, user_id, userbot_id, target)
        except asyncio.TimeoutError:
            await bot.send_message(user_id, "Process timed out.")


    elif data == "select_from_ub":
        userbot_id = temp.UNEQUIFY_USERBOT_ID.get(user_id)
        if not userbot_id: return await bot.send_message(user_id, "Error: Bot selection lost.")
        
        userbot_config = await db.get_bot(user_id, userbot_id)
        if not userbot_config: return await bot.send_message(user_id, "Userbot not found.")
        
        status_msg = await bot.send_message(user_id, "`⏳ Fetching chats...`")

        chats, serial, text = {}, 1, "Reply with the number or Chat ID of the target channel.\n\n"
        try:
            async with CLIENT().client(userbot_config) as userbot:
                async for dialog in userbot.get_dialogs(limit=50): # Limit to 50 for performance
                    chats[str(serial)] = dialog.chat
                    chats[str(dialog.chat.id)] = dialog.chat
                    text += f"<b>{serial}.</b> {dialog.chat.title} (<code>{dialog.chat.id}</code>)\n"
                    serial += 1
            
            await status_msg.delete() # Remove "Fetching" message
            
            try:
                ask_msg = await bot.ask(user_id, text, timeout=300, parse_mode=ParseMode.HTML)
                selected_chat = chats.get(ask_msg.text.strip())
                if not selected_chat:
                    return await ask_msg.reply("Invalid selection. Please start over.")
                
                await process_unequify_target(bot, ask_msg, user_id, userbot_id, selected_chat.id)

            except asyncio.TimeoutError:
                await bot.send_message(user_id, "Process timed out.")

        except Exception as e:
            await bot.send_message(user_id, f"An error occurred: `{e}`")

    elif data.startswith("toggle_"):
        _, current_state, index_str, session_id = data.split("_", 3)
        index = int(index_str)
        state_list = list(current_state)
        state_list[index] = '1' if state_list[index] == '0' else '0'
        new_state = "".join(state_list)
        await query.message.edit_reply_markup(create_selection_keyboard(new_state, session_id))
        await query.answer()

    elif data.startswith("startscan_"):
        _, selection_state, session_id = data.split("_", 2)
        await start_deduplication(bot, query, selection_state, session_id)

async def start_deduplication(bot: Client, callback_query: CallbackQuery, selection_state: str, session_id: str):
    status_message = await bot.send_message(callback_query.from_user.id, "`Processing...`")
    user_id = callback_query.from_user.id
    
    range_session = temp.RANGE_SESSIONS.pop(session_id, None)
    if not range_session:
        return await status_message.edit("Error: Session expired or invalid.")

    userbot_id = temp.UNEQUIFY_USERBOT_ID.pop(user_id, None)
    if not userbot_id:
        return await status_message.edit("Error: Bot selection lost.")

    userbot_config = await db.get_bot(user_id, userbot_id)
    if not userbot_config:
        return await status_message.edit("Error: Userbot not found.")

    target_channel, start_id, end_id = range_session['from_chat_id'], min(range_session['start_id'], range_session['end_id']), max(range_session['start_id'], range_session['end_id'])
    
    await status_message.edit(f"`Initializing userbot session...`")

    seen_identifiers, duplicates_to_delete = set(), []
    total_scanned, total_deleted = 0, 0
    total_in_range = abs(end_id - start_id) + 1

    try:
        async with CLIENT().client(userbot_config) as userbot:
            chat = await userbot.get_chat(target_channel)
            message_ids_to_scan = list(range(start_id, end_id + 1))

            for i in range(0, len(message_ids_to_scan), 200):
                chunk = message_ids_to_scan[i:i+200]
                messages = await userbot.get_messages(chat.id, chunk)

                for msg in messages:
                    if not msg: continue
                    total_scanned += 1
                    identifier = None
                    
                    # --- FIXED DEDUPLICATION LOGIC ---
                    if selection_state[0] == '1' and msg.text: 
                        identifier = msg.text.strip()
                    elif selection_state[1] == '1' and (msg.photo or msg.video):
                        media_obj = msg.photo or msg.video
                        if media_obj: identifier = getattr(media_obj, 'file_unique_id', None)
                    elif selection_state[2] == '1' and msg.audio: 
                        identifier = msg.audio.file_unique_id
                    elif selection_state[3] == '1' and msg.document: 
                        identifier = msg.document.file_unique_id
                    elif selection_state[4] == '1' and msg.sticker: 
                        identifier = msg.sticker.file_unique_id
                    # --- END OF FIX ---

                    if identifier and identifier in seen_identifiers:
                        duplicates_to_delete.append(msg.id)
                    elif identifier:
                        seen_identifiers.add(identifier)

                if len(duplicates_to_delete) >= 100:
                    await userbot.delete_messages(chat_id=chat.id, message_ids=duplicates_to_delete)
                    total_deleted += len(duplicates_to_delete)
                    duplicates_to_delete.clear()
                    try:
                        progress_text = f"Scanned: {total_scanned}/{total_in_range}, Deleted: {total_deleted}"
                        await status_message.edit(Translation.DUPLICATE_TEXT.format(total=total_in_range, scanned=total_scanned, deleted=total_deleted, progress=progress_text))
                    except FloodWait: pass
                    await asyncio.sleep(5)

            if duplicates_to_delete:
                await userbot.delete_messages(chat_id=chat.id, message_ids=duplicates_to_delete)
                total_deleted += len(duplicates_to_delete)

            await status_message.edit(f"✓ **Deduplication Complete!**\n\n**Messages Scanned:** `{total_scanned}`\n**Duplicates Deleted:** `{total_deleted}`")
    except Exception as e:
        await status_message.edit(f"❌ **An unexpected error occurred.**\n\n`{e}`")
