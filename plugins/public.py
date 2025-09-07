import re
import asyncio
import random
from .utils import STS, start_range_selection, update_range_message
from .test import CLIENT
from database import db
from config import temp
from translation import Translation
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait, UserNotParticipant
from pyrogram.errors.exceptions.not_acceptable_406 import ChannelPrivate as PrivateChat
from pyrogram.errors.exceptions.bad_request_400 import ChannelInvalid, ChatAdminRequired, UsernameInvalid, UsernameNotModified, ChannelPrivate, PeerIdInvalid
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove

SYD = ["https://files.catbox.moe/3lwlbm.png"]


#===================Run Function===================#

@Client.on_message(filters.private & filters.command(["fwd", "forward"]))
async def run(bot, message):
    user_id = message.from_user.id
    
    # Explicitly check if the user is banned
    ban_status = await db.get_ban_status(user_id)
    if ban_status["is_banned"]:
        return await message.reply_text(f"Access denied.\n\nReason: {ban_status['ban_reason']}")

    bots = await db.get_bots(user_id)
    if not bots:
        return await message.reply("Add a bot or userbot to proceed.\n( >⁠.⁠< ) --> /settings")

    if len(bots) == 1:
        await choose_target_chat(bot, message, user_id, bots[0]['id'])
    else:
        buttons = []
        for _bot in bots:
            bot_name = _bot.get('name') or _bot.get('username', f"ID: {_bot['id']}")
            buttons.append([InlineKeyboardButton(bot_name, callback_data=f"select_bot_{_bot['id']}")])
        buttons.append([InlineKeyboardButton("« Cancel", callback_data="close_btn")])
        await message.reply_photo(
            photo=random.choice(SYD),
            caption="<b>Select a Bot or Userbot</b>\n\nChoose one to use for forwarding.",
            reply_markup=InlineKeyboardMarkup(buttons),
            quote=True
        )

@Client.on_callback_query(filters.regex(r'^select_bot_'))
async def select_bot_callback(bot, query):
    bot_id = int(query.data.split('_')[2])
    user_id = query.from_user.id
    await query.message.delete()
    await choose_target_chat(bot, query.message, user_id, bot_id)

async def choose_target_chat(bot, message, user_id, bot_id):
    buttons = []
    channels = await db.get_user_channels(user_id)
    if not channels:
       return await message.reply_text("Add a target channel first.\n( >⁠.⁠< ) --> /settings")

    if len(channels) > 0:
       # Use a set to store unique channel IDs to prevent duplicate buttons
       unique_channels = []
       seen_ids = set()
       for channel in channels:
           if channel['chat_id'] not in seen_ids:
               unique_channels.append(channel)
               seen_ids.add(channel['chat_id'])

       for channel in unique_channels:
           buttons.append([InlineKeyboardButton(f"{channel['title']}", callback_data=f"fwd_target_{channel['chat_id']}_{bot_id}")])

       buttons.append([InlineKeyboardButton("« Cancel", callback_data="close_btn")])

       await message.reply_photo(
           photo=random.choice(SYD),
           caption=Translation.TO_MSG,
           reply_markup=InlineKeyboardMarkup(buttons),
           quote=True
       )
    else:
       return await message.reply_text("Add a target channel first.\n( >⁠.⁠< ) --> /settings")

@Client.on_callback_query(filters.regex(r'^fwd_target_'))
async def get_target_chat(bot, query):
    await query.answer()
    user_id = query.from_user.id
    toid = int(query.data.split('_')[2])
    bot_id = int(query.data.split('_')[3])

    # Store the selected bot_id in a user-specific session
    temp.FORWARD_BOT_ID[user_id] = bot_id

    await query.message.delete()

    try:
        await bot.send_photo(
            chat_id=query.message.chat.id,
            photo=random.choice(SYD),
            caption=Translation.FROM_MSG,
            quote=True
        )
        fromid_msg = await bot.listen(chat_id=query.message.chat.id, timeout=300)
    except asyncio.TimeoutError:
        return await bot.send_message(query.message.chat.id, Translation.CANCEL)

    if fromid_msg.text and fromid_msg.text.startswith('/'):
        return await fromid_msg.reply(Translation.CANCEL)

    last_msg_id = 0
    if fromid_msg.text and not fromid_msg.forward_date:
        regex = re.compile(r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$")
        match = regex.match(fromid_msg.text.replace("?single", ""))
        if not match:
            return await fromid_msg.reply('Invalid Link. (╯°□°）╯︵ ┻━┻')
        chat_id = match.group(4)
        last_msg_id = int(match.group(5))
        if chat_id.isnumeric():
            chat_id  = int(("-100" + chat_id))
    elif fromid_msg.forward_from_chat and fromid_msg.forward_from_chat.type == enums.ChatType.CHANNEL:
        last_msg_id = fromid_msg.forward_from_message_id
        chat_id = fromid_msg.forward_from_chat.username or fromid_msg.forward_from_chat.id
    else:
        return await fromid_msg.reply_text("Invalid input. A message link or forwarded message is required.")

    try:
        # Use the selected bot/userbot to get chat info, not the main bot
        selected_bot_config = await db.get_bot(user_id, bot_id)
        if not selected_bot_config:
            return await fromid_msg.reply("Selected bot configuration not found.")

        async with CLIENT().client(selected_bot_config) as temp_client:
            chat_info = await temp_client.get_chat(chat_id)
            title = chat_info.title
            if last_msg_id == 0:
                async for last_message in temp_client.get_chat_history(chat_id, limit=1):
                    last_msg_id = last_message.id
                    break
                    
    except (PrivateChat, ChannelInvalid, PeerIdInvalid):
        title = "A Private Chat"
    except (UsernameInvalid, UsernameNotModified):
        return await fromid_msg.reply('Invalid Link specified.')
    except Exception as e:
        return await fromid_msg.reply(f'An error occurred: {e}')

    await start_range_selection(bot, query, from_chat_id=chat_id, from_title=title, to_chat_id=toid, last_msg_id=last_msg_id, final_callback_prefix="fwd_final")
    await fromid_msg.delete()


async def show_fwd_confirmation(bot, session_id, forward_all=False):
    session = temp.RANGE_SESSIONS.get(session_id)
    if not session: return

    user_id = session['user_id']
    # Retrieve bot_id from the user-specific session
    bot_id = temp.FORWARD_BOT_ID.get(user_id)
    if not bot_id:
        return await bot.send_message(chat_id=session['chat_id'], text="Error: Bot selection lost. Please start over.")

    _bot = await db.get_bot(user_id, bot_id)
    channels = await db.get_user_channels(user_id)
    to_title = next((c['title'] for c in channels if c['chat_id'] == session['to_chat_id']), 'Unknown')

    forward_id = f"{user_id}-{session_id}"

    if forward_all:
        start_id = 1
        end_id = session['last_msg_id']
        message_range_text = "All Messages"
    else:
        start_id = session['start_id']
        end_id = session['end_id']
        message_range_text = f"{start_id} to {end_id}"

    if session['order'] == 'desc' and not forward_all:
        start_id, end_id = end_id, start_id

    bot_name = _bot.get('name') or _bot.get('username', 'N/A')
    bot_uname = _bot.get('username', '')

    buttons = [[
        InlineKeyboardButton('✓ Yes', callback_data=f"start_public_{forward_id}"),
        InlineKeyboardButton('« No', callback_data="close_btn")
    ]]
    reply_markup = InlineKeyboardMarkup(buttons)
    await bot.send_message(
        chat_id=session['chat_id'],
        text=Translation.DOUBLE_CHECK.format(
            botname=bot_name,
            botuname=bot_uname,
            from_chat=session['from_title'],
            to_chat=to_title,
            message_range=message_range_text
        ),
        disable_web_page_preview=True,
        reply_markup=reply_markup
    )

    # For "Forward All", start_id is None to signal get_chat_history usage
    final_start_id = start_id if not forward_all else None
    final_end_id = end_id if not forward_all else session['last_msg_id']

    STS(forward_id).store(
        From=session['from_chat_id'],
        to=session['to_chat_id'],
        start_id=final_start_id,
        end_id=final_end_id,
        order=session['order']
    )
    temp.RANGE_SESSIONS.pop(session_id, None)
    # Clean up the session data
    temp.FORWARD_BOT_ID.pop(user_id, None)

# --- Generic Range Selection Callbacks ---

@Client.on_callback_query(filters.regex(r"^range_info"))
async def info_range_button(bot, query):
    await query.answer("Displays the current range and order selection.", show_alert=False)

@Client.on_callback_query(filters.regex(r"^range_all_"))
async def forward_all_messages(bot, query):
    _, session_id = query.data.split("_", 1)
    session = temp.RANGE_SESSIONS.get(session_id)
    if not session or session['user_id'] != query.from_user.id:
        return await query.answer("Not for this user!", show_alert=True)

    await query.message.delete()
    await show_fwd_confirmation(bot, session_id, forward_all=True)

@Client.on_callback_query(filters.regex(r"^range_edit_"))
async def edit_range_value(bot, query):
    action, value_type, session_id = query.data.split("_", 2)
    session = temp.RANGE_SESSIONS.get(session_id)
    if not session or session['user_id'] != query.from_user.id:
        return await query.answer("Not for this user!", show_alert=True)

    await query.answer()
    try:
        ask_msg = await bot.ask(query.message.chat.id, f"Send the new **{value_type.upper()} ID**.", timeout=60)
        if ask_msg.text and ask_msg.text.isdigit():
            new_id = int(ask_msg.text)
            session[f'{value_type}_id'] = new_id
            await update_range_message(bot, session_id, message=query.message)
        else:
            await ask_msg.reply("Invalid ID. A number is required.")
    except asyncio.TimeoutError:
        await bot.send_message(query.message.chat.id, "Process cancelled. Timed out.")
    except Exception as e:
        print(f"Error asking for range value: {e}")

@Client.on_callback_query(filters.regex(r"^range_swap_"))
async def swap_range_order(bot, query):
    _, session_id = query.data.split("_", 1)
    session = temp.RANGE_SESSIONS.get(session_id)
    if not session or session['user_id'] != query.from_user.id:
        return await query.answer("Not for this user!", show_alert=True)

    session['order'] = 'desc' if session['order'] == 'asc' else 'asc'
    await update_range_message(bot, session_id, message=query.message)
    await query.answer(f"Order swapped!")

@Client.on_callback_query(filters.regex(r"^range_confirm_"))
async def confirm_range_selection(bot, query):
    _, session_id = query.data.split("_", 1)
    session = temp.RANGE_SESSIONS.get(session_id)
    if not session or session['user_id'] != query.from_user.id:
        return await query.answer("Not for this user!", show_alert=True)

    await query.message.delete()

    if session['final_callback'] == 'fwd_final':
        await show_fwd_confirmation(bot, session_id, forward_all=False)
    elif session['final_callback'] == 'uneq_final':
        await query.message.reply_text(
            "Range selected. Now, select message types to deduplicate.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Proceed to Type Selection", callback_data=f"uneq_types_{session_id}")]]))


@Client.on_callback_query(filters.regex(r"^range_cancel_"))
async def cancel_range_selection(bot, query):
    _, session_id = query.data.split("_", 1)
    session = temp.RANGE_SESSIONS.get(session_id)
    if not session or session['user_id'] != query.from_user.id:
        return await query.answer("Not for this user!", show_alert=True)

    # Clean up any related session data
    temp.FORWARD_BOT_ID.pop(query.from_user.id, None)
    temp.UNEQUIFY_USERBOT_ID.pop(query.from_user.id, None)
    temp.RANGE_SESSIONS.pop(session_id, None)
    
    await query.message.edit_text("Operation cancelled.")
    await query.answer()

@Client.on_callback_query(filters.regex("check_subscription"))
async def check_subscription(client, callback_query):
    # This handler is no longer needed with the removal of force subscribe.
    # It can be safely removed or left as-is, it won't be called.
    await callback_query.answer("This feature is disabled.", show_alert=True)
