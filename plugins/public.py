import re
import asyncio
from .utils import STS, start_range_selection, update_range_message
from database import db
from config import temp
from translation import Translation
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait, UserNotParticipant
from pyrogram.errors.exceptions.not_acceptable_406 import ChannelPrivate as PrivateChat
from pyrogram.errors.exceptions.bad_request_400 import ChannelInvalid, ChatAdminRequired, UsernameInvalid, UsernameNotModified, ChannelPrivate
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove

SYD_CHANNELS = ["norFederation"]

#===================Run Function===================#

@Client.on_message(filters.private & filters.command(["fwd", "forward"]))
async def run(bot, message):
    user_id = message.from_user.id
    bots = await db.get_bots(user_id)
    if not bots:
        return await message.reply("Yᴏᴜ Dɪᴅ Nᴏᴛ Aᴅᴅᴇᴅ Aɴʏ Bᴏᴛ Oʀ UꜱᴇʀBᴏᴛ. Pʟᴇᴀꜱᴇ Aᴅᴅ Oɴᴇ Uꜱɪɴɢ /settings !")

    if len(bots) == 1:
        await choose_target_chat(bot, message, bots[0]['id'])
    else:
        buttons = []
        for _bot in bots:
            bot_name = _bot.get('name') or _bot.get('username', f"ID: {_bot['id']}")
            buttons.append([InlineKeyboardButton(bot_name, callback_data=f"select_bot_{_bot['id']}")])
        buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="close_btn")])
        await message.reply_text("<b><u>Select a Bot or Userbot</u></b>\n\nChoose the one you want to use for forwarding.", reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex(r'^select_bot_'))
async def select_bot_callback(bot, query):
    bot_id = int(query.data.split('_')[2])
    await query.message.delete()
    await choose_target_chat(bot, query.message, bot_id)

async def choose_target_chat(bot, message, bot_id):
    buttons = []
    user_id = message.from_user.id
    channels = await db.get_user_channels(user_id)
    if not channels:
       return await message.reply_text("Please Set A To Channel In /settings Before Forwarding")

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

       buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="close_btn")])

       await message.reply_text("<b><u>Cʜᴏᴏꜱᴇ Tᴀʀɢᴇᴛ Cʜᴀᴛ</u></b>\n\nCʜᴏᴏꜱᴇ Yᴏᴜʀ Tᴀʀɢᴇᴛ Cʜᴀᴛ Fʀᴏᴍ Tʜᴇ Gɪᴠᴇɴ Bᴜᴛᴛᴏɴꜱ.", reply_markup=InlineKeyboardMarkup(buttons))
    else:
       return await message.reply_text("Please Set A To Channel In /settings Before Forwarding")

@Client.on_callback_query(filters.regex(r'^fwd_target_'))
async def get_target_chat(bot, query):
    await query.answer()
    user_id = query.from_user.id
    toid = int(query.data.split('_')[2])
    bot_id = int(query.data.split('_')[3])

    # Store the selected bot_id in a user-specific session
    temp.FORWARD_SESSIONS[user_id] = bot_id

    await query.message.delete()

    try:
        fromid_msg = await bot.ask(query.message.chat.id, Translation.FROM_MSG, timeout=300)
    except asyncio.TimeoutError:
        return await bot.send_message(query.message.chat.id, Translation.CANCEL)

    if fromid_msg.text and fromid_msg.text.startswith('/'):
        return await fromid_msg.reply(Translation.CANCEL)

    last_msg_id = 0
    if fromid_msg.text and not fromid_msg.forward_date:
        regex = re.compile(r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$")
        match = regex.match(fromid_msg.text.replace("?single", ""))
        if not match:
            return await fromid_msg.reply('Invalid Link')
        chat_id = match.group(4)
        last_msg_id = int(match.group(5))
        if chat_id.isnumeric():
            chat_id  = int(("-100" + chat_id))
    elif fromid_msg.forward_from_chat and fromid_msg.forward_from_chat.type == enums.ChatType.CHANNEL:
        last_msg_id = fromid_msg.forward_from_message_id
        chat_id = fromid_msg.forward_from_chat.username or fromid_msg.forward_from_chat.id
    else:
        return await fromid_msg.reply_text("Invalid Input!")

    try:
        chat_info = await bot.get_chat(chat_id)
        title = chat_info.title
        # If last_msg_id is not from a link, get the latest message id
        if last_msg_id == 0:
            async for last_message in bot.get_chat_history(chat_id, limit=1):
                last_msg_id = last_message.id
                break
    except (PrivateChat, ChannelInvalid):
        title = "Private Chat"
    except (UsernameInvalid, UsernameNotModified):
        return await fromid_msg.reply('Invalid Link Specified.')
    except Exception as e:
        return await fromid_msg.reply(f'Errors - {e}')

    await start_range_selection(bot, query, from_chat_id=chat_id, from_title=title, to_chat_id=toid, last_msg_id=last_msg_id, final_callback_prefix="fwd_final")
    await fromid_msg.delete()


async def show_fwd_confirmation(bot, session_id, forward_all=False):
    session = temp.RANGE_SESSIONS.get(session_id)
    if not session: return

    user_id = session['user_id']
    # Retrieve bot_id from the user-specific session
    bot_id = temp.FORWARD_SESSIONS.get(user_id)
    if not bot_id:
        return await bot.send_message(chat_id=session['chat_id'], text="Error: Could not determine which bot to use. Please start over.")

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
        InlineKeyboardButton('Yᴇꜱ', callback_data=f"start_public_{forward_id}"),
        InlineKeyboardButton('Nᴏ', callback_data="close_btn")
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
    temp.FORWARD_SESSIONS.pop(user_id, None)

# --- Generic Range Selection Callbacks ---

@Client.on_callback_query(filters.regex(r"^range_info"))
async def info_range_button(bot, query):
    await query.answer("This button displays the current range and order selection.", show_alert=False)

@Client.on_callback_query(filters.regex(r"^range_all_"))
async def forward_all_messages(bot, query):
    _, session_id = query.data.split("_", 1)
    session = temp.RANGE_SESSIONS.get(session_id)
    if not session or session['user_id'] != query.from_user.id:
        return await query.answer("This is not for you!", show_alert=True)

    await query.message.delete()
    await show_fwd_confirmation(bot, session_id, forward_all=True)

@Client.on_callback_query(filters.regex(r"^range_edit_"))
async def edit_range_value(bot, query):
    action, value_type, session_id = query.data.split("_", 2)
    session = temp.RANGE_SESSIONS.get(session_id)
    if not session or session['user_id'] != query.from_user.id:
        return await query.answer("This is not for you!", show_alert=True)

    await query.answer()
    try:
        ask_msg = await bot.ask(query.message.chat.id, f"Please send the new **{value_type.upper()} ID**.", timeout=60)
        if ask_msg.text and ask_msg.text.isdigit():
            new_id = int(ask_msg.text)
            session[f'{value_type}_id'] = new_id
            await update_range_message(bot, session_id, message=query.message)
        else:
            await ask_msg.reply("Invalid ID. Please enter a number.")
    except asyncio.TimeoutError:
        await bot.send_message(query.message.chat.id, "Process cancelled due to timeout.")
    except Exception as e:
        print(f"Error asking for range value: {e}")

@Client.on_callback_query(filters.regex(r"^range_swap_"))
async def swap_range_order(bot, query):
    _, session_id = query.data.split("_", 1)
    session = temp.RANGE_SESSIONS.get(session_id)
    if not session or session['user_id'] != query.from_user.id:
        return await query.answer("This is not for you!", show_alert=True)

    session['order'] = 'desc' if session['order'] == 'asc' else 'asc'
    await update_range_message(bot, session_id, message=query.message)
    await query.answer(f"Order swapped!")

@Client.on_callback_query(filters.regex(r"^range_confirm_"))
async def confirm_range_selection(bot, query):
    _, session_id = query.data.split("_", 1)
    session = temp.RANGE_SESSIONS.get(session_id)
    if not session or session['user_id'] != query.from_user.id:
        return await query.answer("This is not for you!", show_alert=True)

    await query.message.delete()

    if session['final_callback'] == 'fwd_final':
        await show_fwd_confirmation(bot, session_id, forward_all=False)
    elif session['final_callback'] == 'uneq_final':
        await query.message.reply_text(
            "Range selected! Now, please select the message types to deduplicate.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Proceed to Type Selection", callback_data=f"uneq_types_{session_id}")]]))


@Client.on_callback_query(filters.regex(r"^range_cancel_"))
async def cancel_range_selection(bot, query):
    _, session_id = query.data.split("_", 1)
    session = temp.RANGE_SESSIONS.get(session_id)
    if not session or session['user_id'] != query.from_user.id:
        return await query.answer("This is not for you!", show_alert=True)

    # Clean up any related session data
    temp.FORWARD_SESSIONS.pop(query.from_user.id, None)
    temp.USERBOT_SESSIONS.pop(query.from_user.id, None)
    temp.RANGE_SESSIONS.pop(session_id, None)
    
    await query.message.edit_text("Operation cancelled.")
    await query.answer()

@Client.on_callback_query(filters.regex("check_subscription"))
async def check_subscription(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    not_joined_channels = []

    for channel in SYD_CHANNELS:
        try:
            user = await client.get_chat_member(channel, user_id)
            if user.status in {"kicked", "left"}:
                not_joined_channels.append(channel)
        except UserNotParticipant:
            not_joined_channels.append(channel)

    if not not_joined_channels:
        await callback_query.message.edit_text(
            "**Tʜᴀɴᴋꜱ ✨, Yᴏᴜ ʜᴀᴠᴇ ᴊᴏɪɴᴇᴅ ᴏɴ ᴀʟʟ ᴛʜᴇ ʀᴇqᴜɪʀᴇᴅ ᴄʜᴀɴɴᴇʟꜱ. \nCʟɪᴄᴋ ᴏɴ 😊 😂 /forward ɴᴏᴡ ᴛᴏ ꜱᴛᴀʀᴛ ᴛʜᴇ ᴩʀᴏᴄᴇꜱꜱ.....⚡**"
        )
        await callback_query.message.reply("🎊")
    else:
        buttons = [[InlineKeyboardButton(text=f"✧ Jᴏɪɴ {channel.capitalize().replace('_', ' ')} ✧", url=f"https://t.me/{channel}")] for channel in not_joined_channels]
        buttons.append([InlineKeyboardButton(text="✧ Jᴏɪɴ Bᴀᴄᴋ Uᴩ ✧", url="https://t.me/+bAsrcnckBNdkMjVi")])
        buttons.append([InlineKeyboardButton(text="☑ ᴊᴏɪɴᴇᴅ ☑", callback_data="check_subscription")])

        text = "**Sᴛɪʟʟ 🥲, ʏᴏᴜ ʜᴀᴠᴇɴᴛ ᴊᴏɪɴᴇᴅ ɪɴ ᴏᴜʀ ᴀʟʟ ʀᴇqᴜɪʀᴇᴅ ᴄʜᴀɴɴᴇʟꜱ, ᴩʟᴇᴀꜱᴇ ᴅᴏ ꜱᴏ ᴛᴏ ᴄᴏɴᴛɪɴᴜᴇ..✨ .**"
        await callback_query.message.edit_text(text=text, reply_markup=InlineKeyboardMarkup(buttons))
