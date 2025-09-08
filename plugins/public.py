import re
import asyncio
import logging
import random
from .utils import STS, start_range_selection, update_range_message
from database import db
from config import temp
from translation import Translation
from pyrogram import Client, filters, enums
from pyrogram.errors import StopPropagation
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery

logger = logging.getLogger(__name__)

# --- Helper Functions ---
def parse_message_input(message):
    """Parses a forwarded message or a message link."""
    if not message or (not message.text and not message.forward_date):
        return None, None, "Invalid input. A message link or forwarded message is required."

    if message.text and not message.forward_date:
        regex = re.compile(r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$")
        match = regex.match(message.text.replace("?single", ""))
        if not match:
            return None, None, 'Invalid Link.'
        chat_id_str, msg_id = match.group(4), int(match.group(5))
        chat_id = int(("-100" + chat_id_str)) if chat_id_str.isnumeric() else chat_id_str
        return chat_id, msg_id, None
    elif message.forward_from_chat and message.forward_from_chat.type == enums.ChatType.CHANNEL:
        msg_id, chat_id = message.forward_from_message_id, message.forward_from_chat.username or message.forward_from_chat.id
        return chat_id, msg_id, None
    else:
        return None, None, "Invalid input. Please forward from a channel or provide a valid message link."

# --- Main /forward Command Flow ---

@Client.on_message(filters.private & filters.command(["fwd", "forward"]))
async def run(bot, message):
    user_id = message.from_user.id
    temp.USER_STATES.pop(user_id, None)

    bots = await db.get_bots(user_id)
    if not bots:
        return await message.reply("Add a bot or userbot to proceed. ( >⁠.⁠< ) --> /settings")

    if len(bots) == 1:
        temp.FORWARD_BOT_ID[user_id] = bots[0]['id']
        await prompt_target_channel(bot, message)
    else:
        buttons = [[InlineKeyboardButton(b.get('name') or f"ID: {b['id']}", callback_data=f"fwd_select_bot_{b['id']}")] for b in bots]
        buttons.append([InlineKeyboardButton("« Cancel", callback_data="close_btn")])
        await message.reply("<b>Select a Bot or Userbot</b>", reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex(r'^fwd_select_bot_'))
async def cb_select_bot(bot, query):
    bot_id = int(query.data.split('_')[-1])
    temp.FORWARD_BOT_ID[query.from_user.id] = bot_id
    await query.message.delete()
    await prompt_target_channel(bot, query.message)

async def prompt_target_channel(bot, message):
    user_id = message.chat.id
    channels = await db.get_user_channels(user_id)
    if not channels:
       return await message.reply("Add a target channel first. ( >⁠.⁠< ) --> /settings")

    buttons = [[InlineKeyboardButton(c['title'], callback_data=f"fwd_target_{c['chat_id']}")] for c in channels]
    buttons.append([InlineKeyboardButton("« Cancel", callback_data="close_btn")])
    await message.reply(Translation.TO_MSG, reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex(r'^fwd_target_'))
async def cb_select_target(bot, query):
    user_id = query.from_user.id
    to_chat_id = int(query.data.split('_')[-1])
    
    # Set state to wait for the source message
    temp.USER_STATES[user_id] = {"state": "awaiting_source", "to_chat_id": to_chat_id, "message_id": query.message.id}
    await query.message.edit_text(Translation.FROM_MSG)

# --- THE ROBUST STATEFUL MESSAGE HANDLER ---

@Client.on_message(filters.private & ~filters.command() & ~filters.edited, group=1)
async def stateful_message_handler(bot, message):
    user_id = message.from_user.id
    state_info = temp.USER_STATES.get(user_id)

    if not state_info:
        return # Not a stateful conversation, let other handlers run

    state = state_info.get("state")
    
    # --- Handler for /forward's source message ---
    if state == "awaiting_source":
        to_chat_id = state_info["to_chat_id"]
        from_chat_id, end_id, error = parse_message_input(message)
        
        # Clean up the prompt message
        try:
            await bot.delete_messages(user_id, state_info["message_id"])
        except: pass
        
        if error:
            await message.reply(error)
            temp.USER_STATES.pop(user_id, None) # Clear state on error
            raise StopPropagation

        start_id = 1
        
        try:
            chat_info = await bot.get_chat(from_chat_id)
            from_title = chat_info.title
        except Exception:
            from_title = "Private/Unknown Chat"
        
        temp.USER_STATES.pop(user_id, None) # Clear state before next step
        await start_range_selection(bot, message, from_chat_id, from_title, to_chat_id, start_id, end_id)
        raise StopPropagation

    # --- Handler for range editing ---
    elif state and state.startswith("awaiting_range_"):
        value_type = state.split("_")[-1]
        session_id = state_info.get("session_id")
        session = temp.RANGE_SESSIONS.get(session_id)

        # Clean up
        temp.USER_STATES.pop(user_id, None)
        try:
            await bot.delete_messages(user_id, state_info["message_id"])
        except: pass

        if session and message.text and message.text.isdigit():
            session[f'{value_type}_id'] = int(message.text)
            await update_range_message(bot, session_id)
        else:
            await message.reply("Invalid ID or session expired. Please start over.")
        raise StopPropagation

    # --- Handler for /unequify manual input ---
    elif state == "awaiting_unequify_manual_target":
        target = message.text
        temp.USER_STATES.pop(user_id, None)
        
        try:
            await bot.delete_messages(user_id, state_info["message_id"])
        except: pass

        from plugins.unequify import unequify_start
        message.command = ["/unequify", target]
        await unequify_start(bot, message)
        raise StopPropagation

    # --- Handler for /unequify chat selection ---
    elif state == "awaiting_unequify_chat_selection":
        chats = state_info.get("chats", {})
        selected_chat = chats.get(message.text.strip())
        
        temp.USER_STATES.pop(user_id, None)
        try:
            await bot.delete_messages(user_id, state_info["message_id"])
        except: pass

        if not selected_chat:
            await message.reply("Invalid selection. Please start over.")
            raise StopPropagation

        userbot_id = temp.UNEQUIFY_USERBOT_ID.get(user_id)
        if not userbot_id:
            await message.reply("Userbot selection lost. Please start over.")
            raise StopPropagation
        
        userbot_config = await db.get_bot(user_id, userbot_id)
        if not userbot_config:
            await message.reply("Userbot config not found.")
            raise StopPropagation

        from plugins.test import CLIENT
        async with CLIENT().client(userbot_config) as temp_client:
            last_msg_id = 0
            async for last_msg in temp_client.get_chat_history(selected_chat.id, limit=1):
                last_msg_id = last_msg.id
            await start_range_selection(bot, message, from_chat_id=selected_chat.id, from_title=selected_chat.title, to_chat_id=None, last_msg_id=last_msg_id, final_callback_prefix="uneq_final")
        raise StopPropagation


# --- Callbacks for Interactive Range Selection ---

@Client.on_callback_query(filters.regex(r"^range_"))
async def range_selection_callbacks(bot, query):
    user_id = query.from_user.id
    parts = query.data.split("_")
    action, session_id = parts[1], parts[-1]

    session = temp.RANGE_SESSIONS.get(session_id)
    if not session or session['user_id'] != user_id:
        return await query.answer("This is not for you, or the session has expired.", show_alert=True)

    if action == "info":
        await query.answer("Displays the current range and order selection.", show_alert=False)

    elif action == "cancel":
        temp.RANGE_SESSIONS.pop(session_id, None)
        await query.message.delete()
        await bot.send_message(user_id, "Operation cancelled.")

    elif action == "swap":
        session['order'] = 'desc' if session['order'] == 'asc' else 'asc'
        await update_range_message(bot, session_id, message=query.message)
        await query.answer(f"Order swapped!")

    elif action == "edit":
        value_type = parts[2]
        temp.USER_STATES[user_id] = {"state": f"awaiting_range_{value_type}", "session_id": session_id, "message_id": query.message.id}
        await query.message.edit_caption(f"Send the new **{value_type.upper()} ID**.")
        
    elif action == "confirm":
        await query.message.delete()
        if session.get('final_callback') == 'fwd_final':
            await show_final_confirmation(bot, session_id)
        elif session.get('final_callback') == 'uneq_final':
            from plugins.unequify import prompt_type_selection
            await prompt_type_selection(bot, query, session_id)


async def show_final_confirmation(bot, session_id):
    session = temp.RANGE_SESSIONS.get(session_id)
    if not session: return

    user_id, bot_id = session['user_id'], temp.FORWARD_BOT_ID.get(session['user_id'])
    if not bot_id: return await bot.send_message(user_id, "Error: Bot selection lost.")

    _bot, channels = await db.get_bot(user_id, bot_id), await db.get_user_channels(user_id)
    to_title = next((c['title'] for c in channels if c['chat_id'] == session['to_chat_id']), 'Unknown')
    
    start_id, end_id = (session['end_id'], session['start_id']) if session['order'] == 'desc' else (session['start_id'], session['end_id'])
    message_range_text = f"{min(start_id, end_id)} to {max(start_id, end_id)}"
    forward_id = f"{user_id}-{session_id}"

    STS(forward_id).store(From=session['from_chat_id'], to=session['to_chat_id'], start_id=start_id, end_id=end_id)

    await bot.send_message(user_id, Translation.DOUBLE_CHECK.format(
            botname=_bot.get('name', 'N/A'), botuname=_bot.get('username', ''),
            from_chat=session['from_title'], to_chat=to_title, message_range=message_range_text),
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton('✓ Yes, Start Forwarding', callback_data=f"start_public_{forward_id}")],
            [InlineKeyboardButton('« No, Cancel', callback_data="close_btn")]
        ]))
    temp.RANGE_SESSIONS.pop(session_id, None)

@Client.on_callback_query(filters.regex(r'^close_btn$'))
async def close_callback(bot, query):
    temp.USER_STATES.pop(query.from_user.id, None)
    await query.message.delete()
