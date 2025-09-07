import re
import asyncio
import random
from .utils import STS, start_range_selection
from .test import CLIENT
from database import db
from config import temp
from translation import Translation
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait
from pyrogram.errors.exceptions.not_acceptable_406 import ChannelPrivate as PrivateChat
from pyrogram.errors.exceptions.bad_request_400 import ChannelInvalid, UsernameInvalid, UsernameNotModified, PeerIdInvalid
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

SYD = ["https://files.catbox.moe/3lwlbm.png"]

# --- Helper Class for Mocking Query Object ---
class MockQuery:
    def __init__(self, user, message):
        self.from_user = user
        self.message = message

# --- Main Command Handlers ---

@Client.on_message(filters.private & filters.command(["fwd", "forward"]))
async def run(bot, message):
    user_id = message.from_user.id
    
    ban_status = await db.get_ban_status(user_id)
    if ban_status["is_banned"]:
        return await message.reply_text(f"Access denied.\n\nReason: {ban_status['ban_reason']}")

    bots = await db.get_bots(user_id)
    if not bots:
        return await message.reply("Add a bot or userbot to proceed.\n( >⁠.⁠< ) --> /settings")

    if temp.USER_STATES.get(user_id):
        return await message.reply("You are already in the middle of a process. Use /cancel to stop it.")

    if len(bots) == 1:
        await choose_target_chat(bot, message, user_id, bots[0]['id'])
    else:
        buttons = [[InlineKeyboardButton(b.get('name') or b.get('username', f"ID: {b['id']}"),
                                         callback_data=f"select_bot_{b['id']}")] for b in bots]
        buttons.append([InlineKeyboardButton("« Cancel", callback_data="close_btn")])
        await message.reply_photo(
            photo=random.choice(SYD),
            caption="<b>Select a Bot or Userbot</b>\n\nChoose one to use for forwarding.",
            reply_markup=InlineKeyboardMarkup(buttons),
            quote=True
        )

@Client.on_message(filters.private & filters.command("cancel"))
async def cancel_operation(bot, message):
    user_id = message.from_user.id
    user_state = temp.USER_STATES.pop(user_id, None)

    if user_state:
        context_message = user_state.get("context_message")
        if context_message:
            try:
                await context_message.edit_text("Operation cancelled.")
            except Exception:
                await message.reply_text("Operation cancelled.")
        else:
            await message.reply_text("Operation cancelled.")
        temp.FORWARD_BOT_ID.pop(user_id, None)
    else:
        await message.reply_text("Nothing to cancel.")

# --- Callback and State Machine Handlers ---

@Client.on_callback_query(filters.regex(r'^select_bot_'))
async def select_bot_callback(bot, query):
    bot_id = int(query.data.split('_')[2])
    await query.message.delete()
    await choose_target_chat(bot, query.message, query.from_user.id, bot_id)

async def choose_target_chat(bot, message, user_id, bot_id):
    channels = await db.get_user_channels(user_id)
    if not channels:
       return await message.reply_text("Add a target channel first.\n( >⁠.⁠< ) --> /settings")

    unique_channels = {c['chat_id']: c for c in channels}.values()
    buttons = [[InlineKeyboardButton(c['title'], callback_data=f"fwd_target_{c['chat_id']}_{bot_id}")] for c in unique_channels]
    buttons.append([InlineKeyboardButton("« Cancel", callback_data="close_btn")])
    
    await message.reply_photo(
        photo=random.choice(SYD),
        caption=Translation.TO_MSG,
        reply_markup=InlineKeyboardMarkup(buttons),
        quote=True
    )

@Client.on_callback_query(filters.regex(r'^fwd_target_'))
async def get_target_chat(bot, query):
    await query.answer()
    user_id = query.from_user.id
    toid = int(query.data.split('_')[2])
    bot_id = int(query.data.split('_')[3])

    temp.USER_STATES[user_id] = {
        "state": "awaiting_source_chat",
        "to_chat_id": toid,
        "bot_id": bot_id,
        "context_message": query.message
    }
    temp.FORWARD_BOT_ID[user_id] = bot_id

    await query.message.edit_caption(
        caption=Translation.FROM_MSG,
        reply_markup=None
    )

@Client.on_message(filters.private & (filters.text | filters.forwarded) & ~filters.command(list(temp.CANCEL.keys()) + ["start", "fwd", "forward", "settings", "cancel"]))
async def handle_source_chat_response(bot, message):
    user_id = message.from_user.id
    user_state = temp.USER_STATES.get(user_id)

    if not user_state or user_state.get("state") != "awaiting_source_chat":
        return

    context_message = user_state.get("context_message")
    toid = user_state["to_chat_id"]
    bot_id = user_state["bot_id"]
    temp.USER_STATES.pop(user_id, None)

    if context_message:
        try:
            await context_message.delete()
        except Exception as e:
            print(f"Could not delete context message: {e}")

    fromid_msg = message
    last_msg_id, chat_id = 0, None

    if fromid_msg.text and not fromid_msg.forward_date:
        regex = re.compile(r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$")
        match = regex.match(fromid_msg.text.replace("?single", ""))
        if match:
            chat_id, last_msg_id = match.group(4), int(match.group(5))
            if chat_id.isnumeric():
                chat_id = int("-100" + chat_id)
    elif fromid_msg.forward_from_chat and fromid_msg.forward_from_chat.type == enums.ChatType.CHANNEL:
        last_msg_id = fromid_msg.forward_from_message_id
        chat_id = fromid_msg.forward_from_chat.username or fromid_msg.forward_from_chat.id

    if not chat_id:
        return await bot.send_message(user_id, "Invalid input. A message link or forwarded message is required.")

    try:
        selected_bot_config = await db.get_bot(user_id, bot_id)
        if not selected_bot_config:
            return await bot.send_message(user_id, "Selected bot configuration not found.")

        async with CLIENT().client(selected_bot_config) as temp_client:
            chat_info = await temp_client.get_chat(chat_id)
            title = chat_info.title
            if last_msg_id == 0:
                async for last_msg in temp_client.get_chat_history(chat_id, limit=1):
                    last_msg_id = last_msg.id
    except (PrivateChat, ChannelInvalid, PeerIdInvalid):
        title = "A Private Chat"
    except (UsernameInvalid, UsernameNotModified):
        return await bot.send_message(user_id, 'Invalid Link specified.')
    except Exception as e:
        return await bot.send_message(user_id, f'An error occurred: {e}')

    mock_query = MockQuery(fromid_msg.from_user, fromid_msg)
    await start_range_selection(bot, mock_query, from_chat_id=chat_id, from_title=title, to_chat_id=toid, last_msg_id=last_msg_id, final_callback_prefix="fwd_final")

# --- Final Confirmation and Range Selection ---

async def show_fwd_confirmation(bot, session_id, forward_all=False):
    session = temp.RANGE_SESSIONS.get(session_id)
    if not session: return

    user_id = session['user_id']
    bot_id = temp.FORWARD_BOT_ID.get(user_id)
    if not bot_id:
        return await bot.send_message(chat_id=session['chat_id'], text="Error: Bot selection lost. Please start over.")

    _bot = await db.get_bot(user_id, bot_id)
    channels = await db.get_user_channels(user_id)
    to_title = next((c['title'] for c in channels if c['chat_id'] == session['to_chat_id']), 'Unknown')
    forward_id = f"{user_id}-{session_id}"

    start_id, end_id = (1, session['last_msg_id']) if forward_all else (session['start_id'], session['end_id'])
    message_range_text = "All Messages" if forward_all else f"{start_id} to {end_id}"
    if session['order'] == 'desc' and not forward_all:
        start_id, end_id = end_id, start_id

    bot_name = _bot.get('name') or _bot.get('username', 'N/A')
    bot_uname = _bot.get('username', '')

    await bot.send_message(
        chat_id=session['chat_id'],
        text=Translation.DOUBLE_CHECK.format(
            botname=bot_name, botuname=bot_uname, from_chat=session['from_title'],
            to_chat=to_title, message_range=message_range_text
        ),
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton('✓ Yes', callback_data=f"start_public_{forward_id}"),
            InlineKeyboardButton('« No', callback_data="close_btn")
        ]])
    )

    STS(forward_id).store(
        From=session['from_chat_id'], to=session['to_chat_id'],
        start_id=start_id if not forward_all else None,
        end_id=end_id if not forward_all else session['last_msg_id'],
        order=session['order']
    )
    temp.RANGE_SESSIONS.pop(session_id, None)
    temp.FORWARD_BOT_ID.pop(user_id, None)

@Client.on_callback_query(filters.regex(r"^range_"))
async def range_callbacks(bot, query):
    user_id = query.from_user.id
    try:
        action, session_id = query.data.split("_", 1)
    except ValueError:
        return await query.answer("Invalid callback data.")

    session = temp.RANGE_SESSIONS.get(session_id)
    if not session or session['user_id'] != user_id:
        return await query.answer("This is not for you!", show_alert=True)

    action_type = action.split('_')[0]

    if action_type == "info":
        await query.answer("Displays the current range and order selection.", show_alert=False)
    elif action_type == "all":
        await query.message.delete()
        await show_fwd_confirmation(bot, session_id, forward_all=True)
    elif action_type == "edit":
        value_type = action.split('_')[1]
        await query.answer()
        try:
            ask_msg = await bot.ask(query.message.chat.id, f"Send the new **{value_type.upper()} ID**.", timeout=60)
            if ask_msg.text and ask_msg.text.isdigit():
                session[f'{value_type}_id'] = int(ask_msg.text)
                from .utils import update_range_message
                await update_range_message(bot, session_id, message=query.message)
            else:
                await ask_msg.reply("Invalid ID. A number is required.")
        except asyncio.TimeoutError:
            await bot.send_message(query.message.chat.id, "Process cancelled. Timed out.")
    elif action_type == "swap":
        session['order'] = 'desc' if session['order'] == 'asc' else 'asc'
        from .utils import update_range_message
        await update_range_message(bot, session_id, message=query.message)
        await query.answer(f"Order swapped!")
    elif action_type == "confirm":
        await query.message.delete()
        if session.get('final_callback') == 'fwd_final':
            await show_fwd_confirmation(bot, session_id, forward_all=False)
        elif session.get('final_callback') == 'uneq_final':
            await query.message.reply_text(
                "Range selected. Now, select message types to deduplicate.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                    "Proceed to Type Selection", callback_data=f"uneq_types_{session_id}")]]))
    elif action_type == "cancel":
        temp.FORWARD_BOT_ID.pop(user_id, None)
        temp.UNEQUIFY_USERBOT_ID.pop(user_id, None)
        temp.RANGE_SESSIONS.pop(session_id, None)
        await query.message.edit_text("Operation cancelled.")
        await query.answer()
