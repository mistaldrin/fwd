import re
import asyncio
import logging
import random
from .utils import STS, start_range_selection, update_range_message
from database import db
from config import temp
from translation import Translation
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove

logger = logging.getLogger(__name__)

# Helper to parse message link or forwarded message
def parse_message_input(message):
    if not message or (not message.text and not message.forward_date):
        return None, None, "Invalid input. A message link or forwarded message is required."

    if message.text and not message.forward_date:
        regex = re.compile(r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$")
        match = regex.match(message.text.replace("?single", ""))
        if not match:
            return None, None, 'Invalid Link.'
        chat_id_str = match.group(4)
        msg_id = int(match.group(5))
        chat_id = int(("-100" + chat_id_str)) if chat_id_str.isnumeric() else chat_id_str
        return chat_id, msg_id, None
    elif message.forward_from_chat and message.forward_from_chat.type == enums.ChatType.CHANNEL:
        msg_id = message.forward_from_message_id
        chat_id = message.forward_from_chat.username or message.forward_from_chat.id
        return chat_id, msg_id, None
    else:
        return None, None, "Invalid input. Please forward from a channel or provide a valid message link."

@Client.on_message(filters.private & filters.command(["fwd", "forward"]))
async def run(bot, message):
    user_id = message.from_user.id
    temp.FORWARD_BOT_ID.pop(user_id, None)

    # --- Step 1: Select Bot ---
    bots = await db.get_bots(user_id)
    if not bots:
        return await message.reply("Add a bot or userbot to proceed. ( >⁠.⁠< ) --> /settings")

    if len(bots) == 1:
        temp.FORWARD_BOT_ID[user_id] = bots[0]['id']
        await choose_target_chat_prompt(bot, message)
    else:
        buttons = [[InlineKeyboardButton(b.get('name') or f"ID: {b['id']}", callback_data=f"fwd_select_bot_{b['id']}")] for b in bots]
        buttons.append([InlineKeyboardButton("« Cancel", callback_data="close_btn")])
        await message.reply("<b>Select a Bot or Userbot</b>\n\nChoose one to use for forwarding.", reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex(r'^fwd_select_bot_'))
async def select_bot_callback(bot, query):
    bot_id = int(query.data.split('_')[-1])
    temp.FORWARD_BOT_ID[query.from_user.id] = bot_id
    await query.message.delete()
    await choose_target_chat_prompt(bot, query.message)

async def choose_target_chat_prompt(bot, message):
    user_id = message.chat.id
    # --- Step 2: Select Target Channel ---
    channels = await db.get_user_channels(user_id)
    if not channels:
       return await message.reply("Add a target channel first. ( >⁠.⁠< ) --> /settings")

    buttons = [[InlineKeyboardButton(c['title'], callback_data=f"fwd_target_{c['chat_id']}")] for c in channels]
    buttons.append([InlineKeyboardButton("« Cancel", callback_data="close_btn")])
    await message.reply(Translation.TO_MSG, reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex(r'^fwd_target_'))
async def select_target_callback(bot, query):
    user_id = query.from_user.id
    to_chat_id = int(query.data.split('_')[-1])
    await query.message.delete()

    try:
        # --- Step 3: Get End Point ---
        end_point_msg = await bot.ask(user_id, Translation.FROM_MSG)
        if end_point_msg.text and end_point_msg.text.lower() == "/cancel": return await end_point_msg.reply(Translation.CANCEL)

        from_chat_id, end_id, error = parse_message_input(end_point_msg)
        if error: return await end_point_msg.reply(error)

        # --- Step 4: Get Start Point ---
        start_point_msg = await bot.ask(user_id, Translation.START_MSG)
        if start_point_msg.text and start_point_msg.text.lower() == "/cancel": return await start_point_msg.reply(Translation.CANCEL)

        start_chat_id, start_id, error = parse_message_input(start_point_msg)
        if error: return await start_point_msg.reply(error)
        
        if from_chat_id != start_chat_id:
            return await start_point_msg.reply("The start and end points must be from the same channel.")

        # --- Step 5: Show Range Selection ---
        try:
            chat_info = await bot.get_chat(from_chat_id)
            from_title = chat_info.title
        except Exception:
            from_title = "Private/Unknown Chat"

        await start_range_selection(bot, query.message, from_chat_id, from_title, to_chat_id, start_id, end_id)

    except asyncio.TimeoutError:
        await bot.send_message(user_id, "Process timed out and was cancelled.")
    except Exception as e:
        logger.error(f"Forwarding setup error for user {user_id}: {e}", exc_info=True)
        await bot.send_message(user_id, f"An unexpected error occurred: `{e}`")


# --- Callbacks for Interactive Range Selection ---

@Client.on_callback_query(filters.regex(r"^range_"))
async def range_selection_callbacks(bot, query):
    user_id = query.from_user.id
    parts = query.data.split("_")
    action = parts[0]
    sub_action = parts[1] if len(parts) > 1 else None
    session_id = parts[-1]

    session = temp.RANGE_SESSIONS.get(session_id)
    if not session or session['user_id'] != user_id:
        return await query.answer("This is not for you, or the session has expired.", show_alert=True)

    if sub_action == "info":
        await query.answer("Displays the current range and order selection.", show_alert=False)

    elif sub_action == "cancel":
        temp.RANGE_SESSIONS.pop(session_id, None)
        await query.message.delete()
        await bot.send_message(user_id, "Operation cancelled.")

    elif sub_action == "swap":
        session['order'] = 'desc' if session['order'] == 'asc' else 'asc'
        await update_range_message(bot, session_id, message=query.message)
        await query.answer(f"Order swapped!")

    elif sub_action == "edit":
        value_type = parts[2] # start or end
        try:
            ask_msg = await bot.ask(user_id, f"Send the new **{value_type.upper()} ID**.", timeout=60)
            if ask_msg.text and ask_msg.text.isdigit():
                session[f'{value_type}_id'] = int(ask_msg.text)
                await query.message.delete()
                await update_range_message(bot, session_id)
            else:
                await ask_msg.reply("Invalid ID. Please send a number.")
        except asyncio.TimeoutError:
            await bot.send_message(user_id, "Timed out.")

    elif sub_action == "confirm":
        await query.message.delete()
        await show_final_confirmation(bot, session_id)

async def show_final_confirmation(bot, session_id):
    session = temp.RANGE_SESSIONS.get(session_id)
    if not session: return

    user_id = session['user_id']
    bot_id = temp.FORWARD_BOT_ID.get(user_id)
    if not bot_id: return await bot.send_message(user_id, "Error: Bot selection lost.")

    _bot = await db.get_bot(user_id, bot_id)
    channels = await db.get_user_channels(user_id)
    to_title = next((c['title'] for c in channels if c['chat_id'] == session['to_chat_id']), 'Unknown')

    start_id = session['start_id']
    end_id = session['end_id']

    # Ensure start_id is always less than end_id for range calculation
    final_start_id = min(start_id, end_id)
    final_end_id = max(start_id, end_id)
    
    if session['order'] == 'desc':
        # The backend will handle the iteration order, just store the absolute range
        pass

    message_range_text = f"{final_start_id} to {final_end_id}"
    forward_id = f"{user_id}-{session_id}"

    sts = STS(forward_id).store(
        From=session['from_chat_id'],
        to=session['to_chat_id'],
        start_id=final_start_id,
        end_id=final_end_id
    )

    await bot.send_message(
        chat_id=user_id,
        text=Translation.DOUBLE_CHECK.format(
            botname=_bot.get('name', 'N/A'), botuname=_bot.get('username', ''),
            from_chat=session['from_title'], to_chat=to_title,
            message_range=message_range_text
        ),
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton('✓ Yes, Start Forwarding', callback_data=f"start_public_{forward_id}")],
            [InlineKeyboardButton('« No, Cancel', callback_data="close_btn")]
        ])
    )
    temp.RANGE_SESSIONS.pop(session_id, None)

@Client.on_callback_query(filters.regex(r'^close_btn$'))
async def close_callback(bot, query):
    await query.message.delete()
    try:
        if query.message.reply_to_message:
            await query.message.reply_to_message.delete()
    except:
        pass
