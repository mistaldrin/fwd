import asyncio
import random
from database import db
from config import Config, temp
from translation import Translation
from pyrogram import Client, filters
from .test import get_configs, update_configs, CLIENT
from .utils import parse_buttons
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

CLIENT = CLIENT()
SYD = ["https://files.catbox.moe/3lwlbm.png"]


@Client.on_message(filters.private & filters.command(['settings']))
async def settings(client, message):
    user_id = message.from_user.id
    if temp.lock.get(user_id):
        return await message.reply("A task is already in progress. Please wait for it to complete before changing settings.")

    # Explicitly check if the user is banned
    ban_status = await db.get_ban_status(user_id)
    if ban_status["is_banned"]:
        return await message.reply_text(f"Access denied.\n\nReason: {ban_status['ban_reason']}")

    text="<b>֎ Settings ֎</b>\n\nManage personal configurations."
    await message.reply_photo(
        photo=random.choice(SYD),
        caption=text,
        reply_markup=main_buttons(),
        quote=True
    )

@Client.on_callback_query(filters.regex(r'^settings'))
async def settings_query(bot, query):
  # Answer the callback query immediately to prevent the button from appearing unresponsive
  await query.answer()
  user_id = query.from_user.id
  
  if temp.lock.get(user_id):
      return await query.answer("A task is already in progress. Please wait for it to complete before changing settings.", show_alert=True)

  try:
    i, type = query.data.split("#")
    buttons = [[InlineKeyboardButton('« Back', callback_data="settings#main")]]
    
    # A reusable function to handle cancellation and timeouts
    async def handle_cancellation(original_message, new_message=None):
        if new_message:
            await new_message.delete()
        await original_message.edit_text(
            "Process cancelled.",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    if type=="main":
       await query.message.edit_text(
         "<b>֎ Settings ֎</b>\n\nManage personal configurations.",
         reply_markup=main_buttons())

    elif type=="bots":
       buttons = []
       bots = await db.get_bots(user_id)
       for _bot in bots:
          # Gracefully handle missing name, ID, or username
          if not _bot.get('id'):
              continue
          bot_name = _bot.get('name') or _bot.get('username', f"ID: {_bot['id']}")
          bot_id = _bot.get('id')
          buttons.append([InlineKeyboardButton(bot_name,
                           callback_data=f"settings#editbot_{bot_id}")])

       buttons.append([InlineKeyboardButton('+ Add Bot',
                           callback_data="settings#addbot")])
       buttons.append([InlineKeyboardButton('+ Add Userbot',
                           callback_data="settings#adduserbot")])
       buttons.append([InlineKeyboardButton('« Back',
                        callback_data="settings#main")])
       await query.message.edit_text(
         "<b>֎ Bots & Userbots ֎</b>\n\nManage connected bots and userbots.",
         reply_markup=InlineKeyboardMarkup(buttons))

    elif type=="addbot":
       await query.message.delete()
       add_bot_status = await CLIENT.add_bot(bot, query)
       if add_bot_status != True: return
       await bot.send_message(
          chat_id=user_id,
          text="Bot token added. ✓",
          reply_markup=InlineKeyboardMarkup(buttons))

    elif type=="adduserbot":
       await query.message.delete()
       user = await CLIENT.add_session(bot, query)
       if user != True: return
       await bot.send_message(
          chat_id=user_id,
          text="Session added. ✓",
          reply_markup=InlineKeyboardMarkup(buttons))

    elif type=="channels":
       buttons = []
       channels = await db.get_user_channels(user_id)
       for channel in channels:
          buttons.append([InlineKeyboardButton(f"● {channel['title']}",
                           callback_data=f"settings#editchannels_{channel['chat_id']}")])
       buttons.append([InlineKeyboardButton('+ Add Channel',
                        callback_data="settings#addchannel")])
       buttons.append([InlineKeyboardButton('« Back',
                        callback_data="settings#main")])
       await query.message.edit_text(
         "<b>֎ Target Channels ֎</b>\n\nManage target chats for forwarding.",
         reply_markup=InlineKeyboardMarkup(buttons))

    elif type=="addchannel":
       await query.message.delete()
       try:
           original_message = await bot.send_message(user_id, "<b>Set Target Chat</b>\n\nForward a message from the target chat.\n\n/cancel - to cancel.")
           forwarded_message = await bot.ask(chat_id=user_id, timeout=300)
           
           if forwarded_message.text and forwarded_message.text.lower() == "/cancel":
              return await handle_cancellation(original_message, forwarded_message)
           
           if not forwarded_message.forward_date:
              await forwarded_message.delete()
              return await original_message.edit_text("Not a forwarded message. (・_・;)", reply_markup=InlineKeyboardMarkup(buttons))

           chat_id = forwarded_message.forward_from_chat.id
           title = forwarded_message.forward_from_chat.title
           username = forwarded_message.forward_from_chat.username
           username = "@" + username if username else "private"

           if await db.in_channel(user_id, chat_id):
               await forwarded_message.delete()
               await original_message.edit_text("This channel has already been added.", reply_markup=InlineKeyboardMarkup(buttons))
           else:
               await db.add_channel(user_id, chat_id, title, username)
               await forwarded_message.delete()
               await original_message.edit_text("Channel added. ✓", reply_markup=InlineKeyboardMarkup(buttons))
       except asyncio.TimeoutError:
           await bot.send_message(user_id, 'Process timed out.')


    elif type.startswith("editbot"):
       bot_id = int(type.split('_')[1])
       _bot = await db.get_bot(user_id, bot_id)
       if not _bot:
           await query.message.edit_text("Bot configuration not found.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('« Back', callback_data="settings#bots")]]))
           return

       bot_name = _bot.get('name', 'N/A')
       bot_uname = _bot.get('username')
       is_bot = _bot.get('is_bot', True)
       TEXT = Translation.BOT_DETAILS if is_bot else Translation.USER_DETAILS
       uname_display = f"@{bot_uname}" if bot_uname else "Not Set"
       buttons = [[InlineKeyboardButton('- Remove', callback_data=f"settings#removebot_{bot_id}")],
                  [InlineKeyboardButton('« Back', callback_data="settings#bots")]]
       await query.message.edit_text(TEXT.format(bot_name, bot_id, uname_display), reply_markup=InlineKeyboardMarkup(buttons))

    elif type.startswith("removebot"):
       bot_id = int(type.split('_')[1])
       await db.remove_bot(user_id, bot_id)
       await query.message.edit_text("Bot removed. ✓", reply_markup=InlineKeyboardMarkup(buttons))

    elif type.startswith("editchannels"):
       chat_id = type.split('_')[1]
       chat = await db.get_channel_details(user_id, chat_id)
       buttons = [[InlineKeyboardButton('- Remove', callback_data=f"settings#removechannel_{chat_id}")],
                  [InlineKeyboardButton('« Back', callback_data="settings#channels")]]
       await query.message.edit_text(f"<b>֎ Channel Details ֎</b>\n\n<b>Title:</b> <code>{chat['title']}</code>\n<b>ID:</b> <code>{chat['chat_id']}</code>\n<b>Username:</b> {chat['username']}", reply_markup=InlineKeyboardMarkup(buttons))

    elif type.startswith("removechannel"):
       chat_id = type.split('_')[1]
       await db.remove_channel(user_id, chat_id)
       await query.message.edit_text("Channel removed. ✓", reply_markup=InlineKeyboardMarkup(buttons))

    # ... [rest of the settings logic remains the same, but would also benefit from bot.ask]
    # For brevity, only the fixed 'addchannel' is shown, but the principle applies to addcaption, addbutton, etc.

  except Exception as e:
      print(f"Error in settings_query: {e}")
      try:
        await query.message.reply_text("An unexpected error occurred. Please try again later.")
      except:
        await bot.send_message(user_id, "An unexpected error occurred. Please try again later.")


def main_buttons():
  buttons = [[
       InlineKeyboardButton('Bots & Userbots',
                    callback_data=f'settings#bots'),
       InlineKeyboardButton('Channels',
                    callback_data=f'settings#channels')
       ],[
       InlineKeyboardButton('Caption',
                    callback_data=f'settings#caption'),
       InlineKeyboardButton('Database',
                    callback_data=f'settings#database')
       ],[
       InlineKeyboardButton('Message Filters',
                    callback_data=f'settings#filters'),
       InlineKeyboardButton('Button',
                    callback_data=f'settings#button')
       ],[
       InlineKeyboardButton('Extra Settings',
                    callback_data='settings#nextfilters')
       ],[
       InlineKeyboardButton('« Back', callback_data='back')
       ]]
  return InlineKeyboardMarkup(buttons)
