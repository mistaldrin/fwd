import asyncio
from database import db
from config import Config
from translation import Translation
from pyrogram import Client, filters
from .test import get_configs, update_configs, CLIENT
from .utils import parse_buttons
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

CLIENT = CLIENT()

@Client.on_message(filters.private & filters.command(['settings']))
async def settings(client, message):
    user_id = message.from_user.id

    # Explicitly check if the user is banned
    ban_status = await db.get_ban_status(user_id)
    if ban_status["is_banned"]:
        return await message.reply_text(f"Access denied.\n\nReason: {ban_status['ban_reason']}")

    text="<b>❖ Settings ❖</b>\n\nManage personal configurations."
    await message.reply_text(
        text=text,
        reply_markup=main_buttons(),
        quote=True
    )

@Client.on_callback_query(filters.regex(r'^settings'))
async def settings_query(bot, query):
  # Answer the callback query immediately to prevent the button from appearing unresponsive
  await query.answer()
  user_id = query.from_user.id

  try:
    i, type = query.data.split("#")
    buttons = [[InlineKeyboardButton('« Back', callback_data="settings#main")]]

    if type=="main":
       await query.message.edit_text(
         "<b>❖ Settings ❖</b>\n\nManage personal configurations.",
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
         "<b>❖ Bots & Userbots ❖</b>\n\nManage connected bots and userbots.",
         reply_markup=InlineKeyboardMarkup(buttons))

    elif type=="addbot":
       await query.message.delete()
       add_bot_status = await CLIENT.add_bot(bot, query)
       if add_bot_status != True: return
       await query.message.reply_text(
          "Bot token added. ✓",
          reply_markup=InlineKeyboardMarkup(buttons))

    elif type=="adduserbot":
       await query.message.delete()
       user = await CLIENT.add_session(bot, query)
       if user != True: return
       await query.message.reply_text(
          "Session added. ✓",
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
         "<b>❖ Target Channels ❖</b>\n\nManage target chats for forwarding.",
         reply_markup=InlineKeyboardMarkup(buttons))

    elif type=="addchannel":
       await query.message.delete()
       try:
           text = await bot.send_message(user_id, "<b>Set Target Chat</b>\n\nForward a message from the target chat.\n\n/cancel - to cancel.")
           chat_ids = await bot.listen(chat_id=user_id, timeout=300)
           if chat_ids.text=="/cancel":
              await chat_ids.delete()
              return await text.edit_text(
                    "Process cancelled.",
                    reply_markup=InlineKeyboardMarkup(buttons))
           elif not chat_ids.forward_date:
              await chat_ids.delete()
              return await text.edit_text("Not a forwarded message. (・_・;)")
           else:
              chat_id = chat_ids.forward_from_chat.id
              title = chat_ids.forward_from_chat.title
              username = chat_ids.forward_from_chat.username
              username = "@" + username if username else "private"

           # Check for duplicate channel before adding
           if await db.in_channel(user_id, chat_id):
               await chat_ids.delete()
               await text.edit_text(
                   "This channel has already been added.",
                   reply_markup=InlineKeyboardMarkup(buttons))
           else:
               await db.add_channel(user_id, chat_id, title, username)
               await chat_ids.delete()
               await text.edit_text(
                   "Channel added. ✓",
                   reply_markup=InlineKeyboardMarkup(buttons))
       except asyncio.exceptions.TimeoutError:
           await text.edit_text('Process timed out.', reply_markup=InlineKeyboardMarkup(buttons))

    elif type.startswith("editbot"):
       bot_id = int(type.split('_')[1])
       _bot = await db.get_bot(user_id, bot_id)
       if not _bot:
           await query.message.edit_text("Bot configuration not found.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('« Back', callback_data="settings#bots")]]))
           return

       # Use .get() for all dictionary access to prevent KeyErrors
       bot_name = _bot.get('name', 'N/A')
       bot_uname = _bot.get('username')
       is_bot = _bot.get('is_bot', True)

       TEXT = Translation.BOT_DETAILS if is_bot else Translation.USER_DETAILS
       # Handle cases where username is None
       uname_display = f"@{bot_uname}" if bot_uname else "Not Set"

       buttons = [[InlineKeyboardButton('- Remove', callback_data=f"settings#removebot_{bot_id}")
                 ],
                 [InlineKeyboardButton('« Back', callback_data="settings#bots")]]
       await query.message.edit_text(
          TEXT.format(bot_name, bot_id, uname_display),
          reply_markup=InlineKeyboardMarkup(buttons))

    elif type.startswith("removebot"):
       bot_id = int(type.split('_')[1])
       await db.remove_bot(user_id, bot_id)
       await query.message.edit_text(
          "Bot removed. ✓",
          reply_markup=InlineKeyboardMarkup(buttons))

    elif type.startswith("editchannels"):
       chat_id = type.split('_')[1]
       chat = await db.get_channel_details(user_id, chat_id)
       buttons = [[InlineKeyboardButton('- Remove', callback_data=f"settings#removechannel_{chat_id}")
                 ],
                 [InlineKeyboardButton('« Back', callback_data="settings#channels")]]
       await query.message.edit_text(
          f"<b>❖ Channel Details ❖</b>\n\n<b>Title:</b> <code>{chat['title']}</code>\n<b>ID:</b> <code>{chat['chat_id']}</code>\n<b>Username:</b> {chat['username']}",
          reply_markup=InlineKeyboardMarkup(buttons))

    elif type.startswith("removechannel"):
       chat_id = type.split('_')[1]
       await db.remove_channel(user_id, chat_id)
       await query.message.edit_text(
          "Channel removed. ✓",
          reply_markup=InlineKeyboardMarkup(buttons))

    elif type=="caption":
       buttons = []
       data = await get_configs(user_id)
       caption = data['caption']
       if caption is None:
          buttons.append([InlineKeyboardButton('+ Add Caption',
                        callback_data="settings#addcaption")])
       else:
          buttons.append([InlineKeyboardButton('View Caption',
                        callback_data="settings#seecaption")])
          buttons[-1].append(InlineKeyboardButton('Delete Caption',
                        callback_data="settings#deletecaption"))
       buttons.append([InlineKeyboardButton('« Back',
                        callback_data="settings#main")])
       await query.message.edit_text(
          "<b>❖ Custom Caption ❖</b>\n\nSet a custom caption for forwarded media.\n\n<b>Placeholders:</b>\n<code>{filename}</code>, <code>{size}</code>, <code>{caption}</code>",
          reply_markup=InlineKeyboardMarkup(buttons))

    elif type=="seecaption":
       data = await get_configs(user_id)
       buttons = [[InlineKeyboardButton('Edit Caption',
                    callback_data="settings#addcaption")
                 ],[
                 InlineKeyboardButton('« Back',
                   callback_data="settings#caption")]]
       await query.message.edit_text(
          f"<b>Current Caption:</b>\n\n<code>{data['caption']}</code>",
          reply_markup=InlineKeyboardMarkup(buttons))

    elif type=="deletecaption":
       await update_configs(user_id, 'caption', None)
       await query.message.edit_text(
          "Custom caption removed. ✓",
          reply_markup=InlineKeyboardMarkup(buttons))

    elif type=="addcaption":
       await query.message.delete()
       try:
           text = await bot.send_message(query.message.chat.id, "Send the new custom caption.\n\n/cancel - to cancel.")
           caption = await bot.listen(chat_id=user_id, timeout=300)
           if caption.text=="/cancel":
              await caption.delete()
              return await text.edit_text(
                    "Process cancelled.",
                    reply_markup=InlineKeyboardMarkup(buttons))
           try:
              caption.text.format(filename='', size='', caption='')
           except KeyError as e:
              await caption.delete()
              return await text.edit_text(
                 f"Invalid placeholder {e}. Try again.",
                 reply_markup=InlineKeyboardMarkup(buttons))
           await update_configs(user_id, 'caption', caption.text)
           await caption.delete()
           await text.edit_text(
              "Custom caption updated. ✓",
              reply_markup=InlineKeyboardMarkup(buttons))
       except asyncio.exceptions.TimeoutError:
           await text.edit_text('Process timed out.', reply_markup=InlineKeyboardMarkup(buttons))

    elif type=="button":
       buttons = []
       button = (await get_configs(user_id))['button']
       if button is None:
          buttons.append([InlineKeyboardButton('+ Add Button',
                        callback_data="settings#addbutton")])
       else:
          buttons.append([InlineKeyboardButton('View Button',
                        callback_data="settings#seebutton")])
          buttons[-1].append(InlineKeyboardButton('Remove Button',
                        callback_data="settings#deletebutton"))
       buttons.append([InlineKeyboardButton('« Back',
                        callback_data="settings#main")])
       await query.message.edit_text(
          "<b>❖ Custom Button ❖</b>\n\nAttach an inline URL button to messages.\n\n<b>Format:</b>\n`[Button Text][buttonurl:https://example.com]`",
          reply_markup=InlineKeyboardMarkup(buttons))

    elif type=="addbutton":
       await query.message.delete()
       try:
           txt = await bot.send_message(user_id, text="**Send the custom button.**\n\n**Format:**\n`[Text][buttonurl:https://example.com]`")
           ask = await bot.listen(chat_id=user_id, timeout=300)
           button = parse_buttons(ask.text.html)
           if not button:
              await ask.delete()
              return await txt.edit_text("Invalid button format.")
           await update_configs(user_id, 'button', ask.text.html)
           await ask.delete()
           await txt.edit_text("Custom button added. ✓",
              reply_markup=InlineKeyboardMarkup(buttons))
       except asyncio.exceptions.TimeoutError:
           await txt.edit_text('Process timed out.', reply_markup=InlineKeyboardMarkup(buttons))

    elif type=="seebutton":
        button = (await get_configs(user_id))['button']
        button = parse_buttons(button, markup=False)
        button.append([InlineKeyboardButton("« Back", "settings#button")])
        await query.message.edit_text(
           "**Current Custom Button:**",
           reply_markup=InlineKeyboardMarkup(button))

    elif type=="deletebutton":
       await update_configs(user_id, 'button', None)
       await query.message.edit_text(
          "Custom button removed.",
          reply_markup=InlineKeyboardMarkup(buttons))

    elif type=="database":
       buttons = []
       db_uri = (await get_configs(user_id))['db_uri']
       if db_uri is None:
          buttons.append([InlineKeyboardButton('+ Add Database URL',
                        callback_data="settings#addurl")])
       else:
          buttons.append([InlineKeyboardButton('View URL',
                        callback_data="settings#seeurl")])
          buttons[-1].append(InlineKeyboardButton('Remove URL',
                        callback_data="settings#deleteurl"))
       buttons.append([InlineKeyboardButton('« Back',
                        callback_data="settings#main")])
       await query.message.edit_text(
          "<b>❖ Database ❖</b>\n\nA MongoDB database is needed to save duplicate file records permanently.",
          reply_markup=InlineKeyboardMarkup(buttons))

    elif type=="addurl":
       await query.message.delete()
       uri = await bot.ask(user_id, "<b>Send the MongoDB connection URL.</b>\n\nGet one from [mongodb.com](https://mongodb.com).", disable_web_page_preview=True)
       if uri.text=="/cancel":
          return await uri.reply_text(
                    "Process cancelled.",
                    reply_markup=InlineKeyboardMarkup(buttons))
       if not uri.text.startswith("mongodb+srv://"):
          return await uri.reply("Invalid MongoDB URL format.",
                     reply_markup=InlineKeyboardMarkup(buttons))
       await update_configs(user_id, 'db_uri', uri.text)
       await uri.reply("Database URL added. ✓",
               reply_markup=InlineKeyboardMarkup(buttons))

    elif type=="seeurl":
       db_uri = (await get_configs(user_id))['db_uri']
       await query.answer(f"Database URL: {db_uri}", show_alert=True)

    elif type=="deleteurl":
       await update_configs(user_id, 'db_uri', None)
       await query.message.edit_text(
          "Database URL removed.",
          reply_markup=InlineKeyboardMarkup(buttons))

    elif type=="filters":
       await query.message.edit_text(
          "<b>❖ Message Filters ❖</b>\n\nConfigure which message types to forward.",
          reply_markup=await filters_buttons(user_id))

    elif type=="nextfilters":
       await query.edit_message_reply_markup(
          reply_markup=await next_filters_buttons(user_id))

    elif type.startswith("updatefilter"):
       i, key, value = type.split('-')
       if value=="True":
          await update_configs(user_id, key, False)
       else:
          await update_configs(user_id, key, True)
       if key in ['poll', 'protect', 'duplicate', 'forward_tag']:
           await query.edit_message_reply_markup(reply_markup=await filters_buttons(user_id))
           return
       await query.edit_message_reply_markup(
          reply_markup=await filters_buttons(user_id))

    elif type.startswith("file_size"):
      settings = await get_configs(user_id)
      size = settings.get('file_size', 0)
      i, limit = size_limit(settings['size_limit'])
      await query.message.edit_text(
         f'<b>❖ Size Limit ❖</b>\n\nSet a file size limit for forwarding.\n\nStatus: Files {limit} `{size} MB` will be forwarded.',
         reply_markup=size_button(size))

    elif type.startswith("update_size"):
      size = int(query.data.split('-')[1])
      # Prevent negative sizes
      if size < 0:
          size = 0
      if size > 2000:
        return await query.answer("Size limit cannot exceed 2000 MB.", show_alert=True)
      await update_configs(user_id, 'file_size', size)
      i, limit = size_limit((await get_configs(user_id))['size_limit'])
      await query.message.edit_text(
         f'<b>❖ Size Limit ❖</b>\n\nSet a file size limit for forwarding.\n\nStatus: Files {limit} `{size} MB` will be forwarded.',
         reply_markup=size_button(int(size)))

    elif type.startswith('update_limit'):
      i, limit, size = type.split('-')
      limit, sts = size_limit(limit)
      await update_configs(user_id, 'size_limit', limit)
      await query.message.edit_text(
         f'<b>❖ Size Limit ❖</b>\n\nSet a file size limit for forwarding.\n\nStatus: Files {sts} `{size} MB` will be forwarded.',
         reply_markup=size_button(int(size)))

    elif type == "add_extension":
      await query.message.delete()
      ext = await bot.ask(user_id, text="Send file extensions to filter (separated by a space).")
      if ext.text == '/cancel':
         return await ext.reply_text(
                    "Process cancelled.",
                    reply_markup=InlineKeyboardMarkup(buttons))
      extensions = ext.text.split(" ")
      extension = (await get_configs(user_id))['extension']
      if extension:
          for extn in extensions:
              extension.append(extn)
      else:
          extension = extensions
      await update_configs(user_id, 'extension', extension)
      await ext.reply_text(
          f"Extensions filter updated. ✓",
          reply_markup=InlineKeyboardMarkup(buttons))

    elif type == "get_extension":
      extensions = (await get_configs(user_id))['extension']
      btn = extract_btn(extensions)
      btn.append([InlineKeyboardButton('+ Add', 'settings#add_extension')])
      btn.append([InlineKeyboardButton('Remove All', 'settings#rmve_all_extension')])
      btn.append([InlineKeyboardButton('« Back', 'settings#main')])
      await query.message.edit_text(
          text='<b>❖ Extension Filter ❖</b>\n\nFiles with these extensions will not be forwarded.',
          reply_markup=InlineKeyboardMarkup(btn))

    elif type == "rmve_all_extension":
      await update_configs(user_id, 'extension', None)
      await query.message.edit_text("All extension filters removed.",
                                     reply_markup=InlineKeyboardMarkup(buttons))
    elif type == "add_keyword":
      await query.message.delete()
      ask = await bot.ask(user_id, text="Send keywords to filter (separated by a space).")
      if ask.text == '/cancel':
         return await ask.reply_text(
                    "Process cancelled.",
                    reply_markup=InlineKeyboardMarkup(buttons))
      keywords = ask.text.split(" ")
      keyword = (await get_configs(user_id))['keywords']
      if keyword:
          for word in keywords:
              keyword.append(word)
      else:
          keyword = keywords
      await update_configs(user_id, 'keywords', keyword)
      await ask.reply_text(
          f"Keywords filter updated. ✓",
          reply_markup=InlineKeyboardMarkup(buttons))

    elif type == "get_keyword":
      keywords = (await get_configs(user_id))['keywords']
      btn = extract_btn(keywords)
      btn.append([InlineKeyboardButton('+ Add', 'settings#add_keyword')])
      btn.append([InlineKeyboardButton('Remove All', 'settings#rmve_all_keyword')])
      btn.append([InlineKeyboardButton('« Back', 'settings#main')])
      await query.message.edit_text(
          text='<b>❖ Keyword Filter ❖</b>\n\nFiles with these keywords in the file name will be forwarded.',
          reply_markup=InlineKeyboardMarkup(btn))

    elif type == "rmve_all_keyword":
      await update_configs(user_id, 'keywords', None)
      await query.message.edit_text("All keyword filters removed.",
                                     reply_markup=InlineKeyboardMarkup(buttons))
    elif type.startswith("alert"):
      alert = type.split('_')[1]
      await query.answer(alert, show_alert=True)

  except Exception as e:
      print(f"Error in settings_query: {e}")
      # Notify the user that an error occurred
      await query.message.reply_text("An unexpected error occurred. Please try again later.")


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

def size_limit(limit):
   if str(limit) == "None":
      return None, ""
   elif str(limit) == "True":
      return True, "over"
   else:
      return False, "under"

def extract_btn(datas):
    i = 0
    btn = []
    if datas:
       for data in datas:
         if i >= 5:
            i = 0
         if i == 0:
            btn.append([InlineKeyboardButton(data, f'settings#alert_{data}')])
            i += 1
            continue
         elif i > 0:
            btn[-1].append(InlineKeyboardButton(data, f'settings#alert_{data}'))
            i += 1
    return btn

def size_button(size):
  buttons = [[
       InlineKeyboardButton('Over',
                    callback_data=f'settings#update_limit-True-{size}'),
       InlineKeyboardButton('Exact',
                    callback_data=f'settings#update_limit-None-{size}'),
       InlineKeyboardButton('Under',
                    callback_data=f'settings#update_limit-False-{size}')
       ],[
       InlineKeyboardButton('+1',
                    callback_data=f'settings#update_size-{size + 1}'),
       InlineKeyboardButton('-1',
                    callback_data=f'settings#update_size-{size - 1}')
       ],[
       InlineKeyboardButton('+10',
                    callback_data=f'settings#update_size-{size + 10}'),
       InlineKeyboardButton('-10',
                    callback_data=f'settings#update_size-{size - 10}')
       ],[
       InlineKeyboardButton('+100',
                    callback_data=f'settings#update_size-{size + 100}'),
       InlineKeyboardButton('-100',
                    callback_data=f'settings#update_size-{size - 100}')
       ],[
       InlineKeyboardButton('« Back',
                    callback_data="settings#main")
     ]]
  return InlineKeyboardMarkup(buttons)

async def filters_buttons(user_id):
  filter = await get_configs(user_id)
  filters = filter['filters']
  buttons = [[
       InlineKeyboardButton('Forward Tag',
                    callback_data=f'settings#updatefilter-forward_tag-{filter["forward_tag"]}'),
       InlineKeyboardButton('✅' if filter['forward_tag'] else '❌',
                    callback_data=f'settings#updatefilter-forward_tag-{filter["forward_tag"]}')
       ],[
       InlineKeyboardButton('Text',
                    callback_data=f'settings#updatefilter-text-{filters["text"]}'),
       InlineKeyboardButton('✅' if filters['text'] else '❌',
                    callback_data=f'settings#updatefilter-text-{filters["text"]}')
       ],[
       InlineKeyboardButton('Documents',
                    callback_data=f'settings#updatefilter-document-{filters["document"]}'),
       InlineKeyboardButton('✅' if filters['document'] else '❌',
                    callback_data=f'settings#updatefilter-document-{filters["document"]}')
       ],[
       InlineKeyboardButton('Videos',
                    callback_data=f'settings#updatefilter-video-{filters["video"]}'),
       InlineKeyboardButton('✅' if filters['video'] else '❌',
                    callback_data=f'settings#updatefilter-video-{filters["video"]}')
       ],[
       InlineKeyboardButton('Photos',
                    callback_data=f'settings#updatefilter-photo-{filters["photo"]}'),
       InlineKeyboardButton('✅' if filters['photo'] else '❌',
                    callback_data=f'settings#updatefilter-photo-{filters["photo"]}')
       ],[
       InlineKeyboardButton('Audio',
                    callback_data=f'settings#updatefilter-audio-{filters["audio"]}'),
       InlineKeyboardButton('✅' if filters['audio'] else '❌',
                    callback_data=f'settings#updatefilter-audio-{filters["audio"]}')
       ],[
       InlineKeyboardButton('Voice',
                    callback_data=f'settings#updatefilter-voice-{filters["voice"]}'),
       InlineKeyboardButton('✅' if filters['voice'] else '❌',
                    callback_data=f'settings#updatefilter-voice-{filters["voice"]}')
       ],[
       InlineKeyboardButton('Animation',
                    callback_data=f'settings#updatefilter-animation-{filters["animation"]}'),
       InlineKeyboardButton('✅' if filters['animation'] else '❌',
                    callback_data=f'settings#updatefilter-animation-{filters["animation"]}')
       ],[
       InlineKeyboardButton('Stickers',
                    callback_data=f'settings#updatefilter-sticker-{filters["sticker"]}'),
       InlineKeyboardButton('✅' if filters['sticker'] else '❌',
                    callback_data=f'settings#updatefilter-sticker-{filters["sticker"]}')
       ],[
       InlineKeyboardButton('Skip Duplicates',
                    callback_data=f'settings#updatefilter-duplicate-{filter["duplicate"]}'),
       InlineKeyboardButton('✅' if filter['duplicate'] else '❌',
                    callback_data=f'settings#updatefilter-duplicate-{filter["duplicate"]}')
       ],[
       InlineKeyboardButton('« Back',
                    callback_data="settings#main")
       ]]
  return InlineKeyboardMarkup(buttons)

async def next_filters_buttons(user_id):
  filter = await get_configs(user_id)
  filters = filter['filters']
  buttons = [[
       InlineKeyboardButton('Poll',
                    callback_data=f'settings#updatefilter-poll-{filters["poll"]}'),
       InlineKeyboardButton('✅' if filters['poll'] else '❌',
                    callback_data=f'settings#updatefilter-poll-{filters["poll"]}')
       ],[
       InlineKeyboardButton('Protect Content',
                    callback_data=f'settings#updatefilter-protect-{filter["protect"]}'),
       InlineKeyboardButton('✅' if filter['protect'] else '❌',
                    callback_data=f'settings#updatefilter-protect-{filter["protect"]}')
       ],[
       InlineKeyboardButton('Size Limit',
                    callback_data='settings#file_size')
       ],[
       InlineKeyboardButton('Extension Filter',
                    callback_data='settings#get_extension')
       ],[
       InlineKeyboardButton('Keyword Filter',
                    callback_data='settings#get_keyword')
       ],[
       InlineKeyboardButton('« Back',
                    callback_data="settings#main")
       ]]
  return InlineKeyboardMarkup(buttons)
