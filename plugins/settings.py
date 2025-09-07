import re
import asyncio
import io
import random
from .utils import STS, start_range_selection, update_range_message
from .test import CLIENT
from database import db
from config import temp
from translation import Translation
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ChatMemberStatus, ParseMode
from pyrogram.errors import FloodWait, ChannelInvalid, UsernameNotOccupied, UsernameInvalid, PeerIdInvalid

SYD = ["https://files.catbox.moe/3lwlbm.png"]


# ------------------------------------------------------------------------------------
# Main /forward command entry point
# ------------------------------------------------------------------------------------
@Client.on_message(filters.private & filters.command(["fwd", "forward"]))
async def run_command(bot: Client, message: Message):
    user_id = message.from_user.id
    
    ban_status = await db.get_ban_status(user_id)
    if ban_status["is_banned"]:
        return await message.reply_text(f"Access denied.\n\nReason: {ban_status['ban_reason']}")

    source_chat_param = " ".join(message.command[1:]) if len(message.command) > 1 else None

    bots = await db.get_bots(user_id)
    if not bots:
        return await message.reply("Add a bot or userbot to proceed.\n( >⁠.⁠< ) --> /settings")

    # Store the source chat parameter if it exists
    temp.USER_STATES[user_id] = {
        "source_chat_param": source_chat_param
    }
    
    # --- Step 1: Select Bot/Userbot ---
    if len(bots) == 1:
        await select_bot_logic(bot, message, user_id, bots[0]['id'])
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

# ------------------------------------------------------------------------------------
# Callback handler for bot selection
# ------------------------------------------------------------------------------------
@Client.on_callback_query(filters.regex(r'^select_bot_'))
async def select_bot_callback(bot: Client, query: CallbackQuery):
    bot_id = int(query.data.split('_')[2])
    await query.message.delete()
    await select_bot_logic(bot, query.message, query.from_user.id, bot_id)


async def select_bot_logic(bot: Client, message: Message, user_id: int, bot_id: int):
    """Handles logic after a bot is selected."""
    # Store the chosen bot_id
    temp.FORWARD_BOT_ID[user_id] = bot_id
    
    # --- Step 2: Select Target Chat ---
    channels = await db.get_user_channels(user_id)
    if not channels:
       return await message.reply_text("Add a target channel first.\n( >⁠.⁠< ) --> /settings")

    unique_channels = {c['chat_id']: c for c in channels}.values()
    buttons = [[InlineKeyboardButton(c['title'], callback_data=f"fwd_target_{c['chat_id']}")] for c in unique_channels]
    buttons.append([InlineKeyboardButton("« Cancel", callback_data="close_btn")])
    
    await message.reply_photo(
        photo=random.choice(SYD),
        caption=Translation.TO_MSG,
        reply_markup=InlineKeyboardMarkup(buttons),
        quote=True
    )

# ------------------------------------------------------------------------------------
# Callback handler for target chat selection
# ------------------------------------------------------------------------------------
@Client.on_callback_query(filters.regex(r'^fwd_target_'))
async def select_target_callback(bot: Client, query: CallbackQuery):
    user_id = query.from_user.id
    to_chat_id = int(query.data.split('_')[2])
    
    user_state = temp.USER_STATES.get(user_id, {})
    source_chat_param = user_state.get("source_chat_param")
    
    bot_id = temp.FORWARD_BOT_ID.get(user_id)
    if not bot_id:
        return await query.message.edit_text("Error: Bot selection lost. Please start over.")

    await query.message.delete()

    # --- Step 3: Determine Source Chat ---
    if source_chat_param:
        # If source was a parameter, process it and go to range selection
        await process_source_chat(bot, query.message, user_id, bot_id, to_chat_id, source_chat_param)
    else:
        # Otherwise, ask the user for the source chat
        await ask_for_source_chat(bot, query.message, user_id, bot_id, to_chat_id)

async def ask_for_source_chat(bot: Client, message: Message, user_id: int, bot_id: int, to_chat_id: int):
    """Asks the user for the source chat, behavior depends on bot/userbot."""
    bot_config = await db.get_bot(user_id, bot_id)
    if not bot_config:
        return await message.reply("Bot configuration not found.")
        
    temp.USER_STATES[user_id] = {
        "state": "awaiting_source_chat",
        "to_chat_id": to_chat_id
    }

    if bot_config.get('is_bot'):
        # For bots, ask for ID/link
        await message.reply(Translation.SOURCE_MSG_BOT)
    else:
        # For userbots, show chat list
        status_msg = await message.reply("`⏳ Fetching userbot chats...`")
        chats = {}
        serial = 1
        text = Translation.SOURCE_MSG_USERBOT + "\n\n"
        try:
            async with CLIENT().client(bot_config) as userbot:
                async for dialog in userbot.get_dialogs(limit=200): # Limit to 200 for performance
                    chats[str(serial)] = dialog.chat
                    chats[str(dialog.chat.id)] = dialog.chat
                    text += f"<b>{serial}.</b> {dialog.chat.title} (<code>{dialog.chat.id}</code>)\n"
                    serial += 1
            temp.USER_STATES[user_id]["chats_cache"] = chats
            await status_msg.edit(text, parse_mode=ParseMode.HTML)
        except Exception as e:
            await status_msg.edit(f"An error occurred: `{e}`")

# ------------------------------------------------------------------------------------
# Message handler for when user provides the source chat
# ------------------------------------------------------------------------------------
@Client.on_message(filters.private & filters.text & ~filters.command("cancel"))
async def source_chat_handler(bot: Client, message: Message):
    user_id = message.from_user.id
    user_state = temp.USER_STATES.get(user_id)

    if not user_state or user_state.get("state") != "awaiting_source_chat":
        return

    to_chat_id = user_state["to_chat_id"]
    bot_id = temp.FORWARD_BOT_ID.get(user_id)
    
    source_input = message.text.strip()

    # If it was a selection from a list
    chats_cache = user_state.get("chats_cache", {})
    selected_chat = chats_cache.get(source_input)
    
    if selected_chat:
        source_input = selected_chat.id

    await message.delete()
    
    # Now process the input (could be ID, link, or username)
    await process_source_chat(bot, message, user_id, bot_id, to_chat_id, source_input)


# ------------------------------------------------------------------------------------
# Core logic to process the source chat and proceed to range selection
# ------------------------------------------------------------------------------------
async def process_source_chat(bot: Client, message: Message, user_id: int, bot_id: int, to_chat_id: int, source_input: str):
    """Gets chat info and proceeds to the range selection screen."""
    
    # Clear the user's state
    temp.USER_STATES.pop(user_id, None)
    
    last_msg_id = 0
    from_chat_id = None

    # Parse link if provided
    regex = re.compile(r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/?(\d+)?")
    match = regex.match(source_input.replace("?single", ""))
    
    if match:
        from_chat_id = match.group(4)
        if from_chat_id.isnumeric():
            from_chat_id = int("-100" + from_chat_id)
    else:
        from_chat_id = source_input # Assume it's a username or ID

    try:
        bot_config = await db.get_bot(user_id, bot_id)
        async with CLIENT().client(bot_config) as temp_client:
            chat_info = await temp_client.get_chat(from_chat_id)
            from_title = chat_info.title
            
            # Get the very last message ID
            async for last_message in temp_client.get_chat_history(chat_info.id, limit=1):
                last_msg_id = last_message.id
                break
            
            # --- Step 4: Show Range Selection ---
            await start_range_selection(
                bot=bot,
                user_id=user_id,
                chat_id=user_id,
                from_chat_id=chat_info.id,
                from_title=from_title,
                to_chat_id=to_chat_id,
                last_msg_id=last_msg_id,
                final_callback_prefix="fwd_final"
            )

    except (UsernameInvalid, PeerIdInvalid, ChannelInvalid) as e:
        await message.reply(f"Could not find the source chat: `{e}`.")
    except Exception as e:
        await message.reply(f"An error occurred: {e}")

# ------------------------------------------------------------------------------------
# Final confirmation and range selection callbacks
# ------------------------------------------------------------------------------------
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
async def range_callbacks(bot, query: CallbackQuery):
    user_id = query.from_user.id
    
    parts = query.data.split("_")
    session_id = parts[-1]
    action_key = "_".join(parts[:-1])

    session = temp.RANGE_SESSIONS.get(session_id)

    if not session or session.get('user_id') != user_id:
        session_uid = session.get('user_id') if session else "None"
        error_text = f"This is not for you! (Session UID: {session_uid}, Your UID: {user_id})"
        return await query.answer(error_text, show_alert=True)

    if action_key == "range_info":
        await query.answer("Displays the current range and order selection.", show_alert=False)

    elif action_key == "range_all":
        await query.message.delete()
        await show_fwd_confirmation(bot, session_id, forward_all=True)

    elif action_key.startswith("range_edit"):
        value_type = action_key.split("_")[2]
        await query.answer()
        try:
            ask_msg = await bot.ask(query.message.chat.id, f"Send the new **{value_type.upper()} ID**.", timeout=60)
            if ask_msg.text and ask_msg.text.isdigit():
                session[f'{value_type}_id'] = int(ask_msg.text)
                await update_range_message(bot, session_id, message=query.message)
            else:
                await ask_msg.reply("Invalid ID. A number is required.")
            await bot.delete_messages(chat_id=query.message.chat.id, message_ids=[ask_msg.request.id, ask_msg.id])
        except asyncio.TimeoutError:
            await bot.send_message(query.message.chat.id, "Process cancelled. Timed out.")

    elif action_key == "range_swap":
        session['order'] = 'desc' if session['order'] == 'asc' else 'asc'
        await update_range_message(bot, session_id, message=query.message)
        await query.answer(f"Order swapped!")

    elif action_key == "range_confirm":
        await query.message.delete()
        if session.get('final_callback') == 'fwd_final':
            await show_fwd_confirmation(bot, session_id, forward_all=False)
        elif session.get('final_callback') == 'uneq_final':
            await query.message.reply_text(
                "Range selected. Now, select message types to deduplicate.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                    "Proceed to Type Selection", callback_data=f"uneq_types_{session_id}")]]))

    elif action_key == "range_cancel":
        temp.FORWARD_BOT_ID.pop(user_id, None)
        temp.UNEQUIFY_USERBOT_ID.pop(user_id, None)
        temp.RANGE_SESSIONS.pop(session_id, None)
        await query.message.edit_text("Operation cancelled.")
        await query.answer()
