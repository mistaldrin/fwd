import re
import asyncio 
from .utils import STS
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
    buttons = []
    user_id = message.from_user.id
    
    # Check for all available bots
    bots = await db.get_all_bots(user_id)
    if not bots:
        return await message.reply("Yᴏᴜ Dɪᴅ Nᴏᴛ Aᴅᴅᴇᴅ Aɴʏ Bᴏᴛ. Pʟᴇᴀꜱᴇ Aᴅᴅ A Bᴏᴛ Uꜱɪɴɢ /settings !")

    channels = await db.get_user_channels(user_id)
    if not channels:
       return await message.reply_text("Please Set A To Channel In /settings Before Forwarding")
    
    # Create buttons for each bot
    for _bot in bots:
        text = f"🤖 {_bot['name']}" if _bot['is_bot'] else f"👤 {_bot['name']}"
        buttons.append([InlineKeyboardButton(text, callback_data=f"fwd_bot_{_bot['id']}")])
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="close_btn")])

    await message.reply_text("<b><u>Cʜᴏᴏꜱᴇ Bᴏᴛ</u></b>\n\nCʜᴏᴏꜱᴇ Tʜᴇ Bᴏᴛ Yᴏᴜ Wᴀɴᴛ To Uꜱᴇ Fᴏʀ Fᴏʀᴡᴀʀᴅɪɴɢ.", reply_markup=InlineKeyboardMarkup(buttons))
        
@Client.on_callback_query(filters.regex(r'^fwd_bot_'))
async def choose_target_chat(bot, query):
    await query.answer()

    user_id = query.from_user.id
    bot_id = int(query.data.split('_')[2])
    
    channels = await db.get_user_channels(user_id)
    
    if len(channels) > 0:
        unique_channels = []
        seen_ids = set()
        for channel in channels:
            if channel['chat_id'] not in seen_ids:
                unique_channels.append(channel)
                seen_ids.add(channel['chat_id'])
               
        buttons = []
        for channel in unique_channels:
            buttons.append([InlineKeyboardButton(f"{channel['title']}", callback_data=f"fwd_target_{bot_id}_{channel['chat_id']}")])
        
        buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="close_btn")]) 
       
        await query.message.edit_text("<b><u>Cʜᴏᴏꜱᴇ Tᴀʀɢᴇᴛ Cʜᴀᴛ</u></b>\n\nCʜᴏᴏꜱᴇ Yᴏᴜʀ Tᴀʀɢᴇᴛ Cʜᴀᴛ Fʀᴏᴍ Tʜᴇ Gɪᴠᴇɴ Bᴜᴛᴛᴏɴꜱ.", reply_markup=InlineKeyboardMarkup(buttons))
    else:
       await query.message.edit_text("Please Set A To Channel In /settings Before Forwarding")
    
@Client.on_callback_query(filters.regex(r'^fwd_target_'))
async def get_source_chat(bot, query):
    await query.answer()

    user_id = query.from_user.id
    bot_id, toid = query.data.split('_')[2:]
    toid = int(toid)
    bot_id = int(bot_id)

    _bot = await db.get_bot(user_id, bot_id)
    channels = await db.get_user_channels(user_id)
    to_title = next((c['title'] for c in channels if c['chat_id'] == toid), 'Unknown')
    
    await query.message.delete()
    
    try:
        fromid = await bot.ask(query.message.chat.id, Translation.FROM_MSG, timeout=300)
    except asyncio.exceptions.TimeoutError:
        return await bot.send_message(query.message.chat.id, Translation.CANCEL)
        
    if fromid.text and fromid.text.startswith('/'):
        return await fromid.reply(Translation.CANCEL)

    if fromid.text and not fromid.forward_date:
        regex = re.compile(r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$")
        match = regex.match(fromid.text.replace("?single", ""))
        if not match:
            return await fromid.reply('Invalid Link')
        chat_id = match.group(4)
        last_msg_id = int(match.group(5))
        if chat_id.isnumeric():
            chat_id  = int(("-100" + chat_id))
    elif fromid.forward_from_chat and fromid.forward_from_chat.type in [enums.ChatType.CHANNEL]:
        last_msg_id = fromid.forward_from_message_id
        chat_id = fromid.forward_from_chat.username or fromid.forward_from_chat.id
        if last_msg_id == None:
           return await fromid.reply_text("This May Be A Forwarded Message From A Group And Sended By Anonymous Admin. Instead Of This Please Send Last Message Link From Group")
    else:
        await fromid.reply_text("Invalid !")
        return 
    
    try:
        title = (await bot.get_chat(chat_id)).title
    except (PrivateChat, ChannelPrivate, ChannelInvalid):
        title = "private" if fromid.text else fromid.forward_from_chat.title
    except (UsernameInvalid, UsernameNotModified):
        return await fromid.reply('Invalid Link Specified.')
    except Exception as e:
        return await fromid.reply(f'Errors - {e}')
    
    skipno = await bot.ask(query.message.chat.id, Translation.SKIP_MSG, timeout=300)
    if skipno.text.startswith('/'):
        return await skipno.reply(Translation.CANCEL)
        
    forward_id = f"{user_id}-{skipno.id}"
    buttons = [[
        InlineKeyboardButton('Yᴇꜱ', callback_data=f"start_public_{forward_id}_{bot_id}"),
        InlineKeyboardButton('Nᴏ', callback_data="close_btn")
    ]]
    reply_markup = InlineKeyboardMarkup(buttons)
    await bot.send_message(
        chat_id=query.message.chat.id,
        text=Translation.DOUBLE_CHECK.format(botname=_bot['name'], botuname=_bot['username'], from_chat=title, to_chat=to_title, skip=skipno.text),
        disable_web_page_preview=True,
        reply_markup=reply_markup
    )
    
    STS(forward_id).store(chat_id, toid, int(skipno.text), int(last_msg_id), bot_id)


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
        # CORRECTED LIST COMPREHENSION #2
        buttons = [
            [
                InlineKeyboardButton(
                    text=f"✧ Jᴏɪɴ {channel.capitalize().replace('_', ' ')} ✧",
                    url=f"https://t.me/{channel}",
                )
            ]
            for channel in not_joined_channels
        ]
        buttons.append(
            [
                InlineKeyboardButton(
                    text="✧ Jᴏɪɴ Bᴀᴄᴋ Uᴩ ✧", url="https://t.me/+bAsrcnckBNdkMjVi"

                )
            ]
        )

        buttons.append(
            [
                InlineKeyboardButton(
                    text="☑ ᴊᴏɪɴᴇᴅ ☑", callback_data="check_subscription"
                )
            ]
        )

        text = "**Sᴛɪʟʟ 🥲, ʏᴏᴜ ʜᴀᴠᴇɴᴛ ᴊᴏɪɴᴇᴅ ɪɴ ᴏᴜʀ ᴀʟʟ ʀᴇqᴜɪʀᴇᴅ ᴄʜᴀɴɴᴇʟꜱ, ᴩʟᴇᴀꜱᴇ ᴅᴏ ꜱᴏ ᴛᴏ ᴄᴏɴᴛɪɴᴜᴇ..✨ .**"
        await callback_query.message.edit_text(
            text=text, reply_markup=InlineKeyboardMarkup(buttons)
     )
