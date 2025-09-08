import asyncio
import random
from database import db
from config import Config
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

  try:
    i, type = query.data.split("#")
    buttons = [[InlineKeyboardButton('« Back', callback_data="settings#main")]]
    
    # A reusable function to handle cancellation and timeouts
    async def handle_cancellation(original_message, new_message):
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
       original_message = await query.message.edit_text("<b>Set Target Chat</b>\n\nForward a message from the target chat.\n\n/cancel - to cancel.")
       try:
           forwarded_message = await bot.ask(chat_id=user_id, text="Forward a message from the target chat to add it.", timeout=300)
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
           await original_message.edit_text('Process timed out.', reply_markup=InlineKeyboardMarkup(buttons))


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
          f"<b>֎ Channel Details ֎</b>\n\n<b>Title:</b> <code>{chat['title']}</code>\n<b>ID:</b> <code>{chat['chat_id']}</code>\n<b>Username:</b> {chat['username']}",
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
          "<b>֎ Custom Caption ֎</b>\n\nSet a custom caption for forwarded media.\n\n<b>Placeholders:</b>\n<code>{filename}</code>, <code>{size}</code>, <code>{caption}</code>",
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
       original_message = await query.message.edit_text("Send the new custom caption.\n\n/cancel - to cancel.")
       try:
           caption_message = await bot.ask(chat_id=user_id, text="Send your new caption.", timeout=300)
           if caption_message.text and caption_message.text.lower() == "/cancel":
               return await handle_cancellation(original_message, caption_message)
           
           try:
              caption_message.text.format(filename='', size='', caption='')
           except KeyError as e:
              await caption_message.delete()
              return await original_message.edit_text(f"Invalid placeholder {e}. Try again.", reply_markup=InlineKeyboardMarkup(buttons))
           
           await update_configs(user_id, 'caption', caption_message.text)
           await caption_message.delete()
           await original_message.edit_text("Custom caption updated. ✓", reply_markup=InlineKeyboardMarkup(buttons))
       except asyncio.TimeoutError:
           await original_message.edit_text('Process timed out.', reply_markup=InlineKeyboardMarkup(buttons))


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
          "<b>֎ Custom Button ֎</b>\n\nAttach an inline URL button to messages.\n\n<b>Format:</b>\n`[Button Text][buttonurl:https://example.com]`",
          reply_markup=InlineKeyboardMarkup(buttons))

    elif type=="addbutton":
       original_message = await query.message.edit_text("**Send the custom button.**\n\n**Format:**\n`[Text][buttonurl:https://example.com]`\n\n/cancel - to cancel.")
       try:
           button_message = await bot.ask(chat_id=user_id, text="Send the button text in the correct format.", timeout=300)
           if button_message.text and button_message.text.lower() == "/cancel":
               return await handle_cancellation(original_message, button_message)

           button_markup = parse_buttons(button_message.text.html)
           if not button_markup:
              await button_message.delete()
              return await original_message.edit_text("Invalid button format.", reply_markup=InlineKeyboardMarkup(buttons))
           
           await update_configs(user_id, 'button', button_message.text.html)
           await button_message.delete()
           await original_message.edit_text("Custom button added. ✓", reply_markup=InlineKeyboardMarkup(buttons))
       except asyncio.TimeoutError:
           await original_message.edit_text('Process timed out.', reply_markup=InlineKeyboardMarkup(buttons))


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
          "<b>֎ Database ֎</b>\n\nA MongoDB database is needed to save duplicate file records permanently.",
          reply_markup=InlineKeyboardMarkup(buttons))

    elif type=="addurl":
       original_message = await query.message.edit_text("<b>Send the MongoDB connection URL.</b>\n\nGet one from [mongodb.com](https://mongodb.com).\n\n/cancel - to cancel.", disable_web_page_preview=True)
       try:
           uri_message = await bot.ask(user_id, "Send your MongoDB URL.", timeout=300)
           if uri_message.text and uri_message.text.lower() == "/cancel":
               return await handle_cancellation(original_message, uri_message)

           if not uri_message.text.startswith("mongodb+srv://"):
              await uri_message.delete()
              return await original_message.edit_text("Invalid MongoDB URL format.", reply_markup=InlineKeyboardMarkup(buttons))
           
           await update_configs(user_id, 'db_uri', uri_message.text)
           await uri_message.delete()
           await original_message.edit_text("Database URL added. ✓", reply_markup=InlineKeyboardMarkup(buttons))
       except asyncio.TimeoutError:
           await original_message.edit_text('Process timed out.', reply_markup=InlineKeyboardMarkup(buttons))


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
          "<b>֎ Message Filters ֎</b>\n\nConfigure which message types to forward.",
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
         f'<b>֎ Size Limit ֎</b>\n\nSet a file size limit for forwarding.\n\nStatus: Files {limit} `{size} MB` will be forwarded.',
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
         f'<b>֎ Size Limit ֎</b>\n\nSet a file size limit for forwarding.\n\nStatus: Files {limit} `{size} MB` will be forwarded.',
         reply_markup=size_button(int(size)))

    elif type.startswith('update_limit'):
      i, limit, size = type.split('-')
      limit, sts = size_limit(limit)
      await update_configs(user_id, 'size_limit', limit)
      await query.message.edit_text(
         f'<b>֎ Size Limit ֎</b>\n\nSet a file size limit for forwarding.\n\nStatus: Files {sts} `{size} MB` will be forwarded.',
         reply_markup=size_button(int(size)))

    elif type == "add_extension":
      original_message = await query.message.edit_text("Send file extensions to filter (separated by a space).\n\n/cancel - to cancel")
      try:
          ext_message = await bot.ask(user_id, text="Send your extensions now.", timeout=300)
          if ext_message.text and ext_message.text.lower() == '/cancel':
              return await handle_cancellation(original_message, ext_message)

          extensions_to_add = ext_message.text.lower().split(" ")
          current_extensions = (await get_configs(user_id))['extension'] or []
          
          # Add only new extensions
          new_extensions = [ext for ext in extensions_to_add if ext not in current_extensions]
          updated_extensions = current_extensions + new_extensions
          
          await update_configs(user_id, 'extension', updated_extensions)
          await ext_message.delete()
          await original_message.edit_text("Extensions filter updated. ✓", reply_markup=InlineKeyboardMarkup(buttons))
      except asyncio.TimeoutError:
          await original_message.edit_text('Process timed out.', reply_markup=InlineKeyboardMarkup(buttons))


    elif type == "get_extension":
      extensions = (await get_configs(user_id))['extension']
      btn = extract_btn(extensions)
      btn.append([InlineKeyboardButton('+ Add', 'settings#add_extension')])
      btn.append([InlineKeyboardButton('Remove All', 'settings#rmve_all_extension')])
      btn.append([InlineKeyboardButton('« Back', 'settings#main')])
      await query.message.edit_text(
          text='<b>֎ Extension Filter ֎</b>\n\nFiles with these extensions will not be forwarded.',
          reply_markup=InlineKeyboardMarkup(btn))

    elif type == "rmve_all_extension":
      await update_configs(user_id, 'extension', None)
      await query.message.edit_text("All extension filters removed.",
                                     reply_markup=InlineKeyboardMarkup(buttons))
    elif type == "add_keyword":
      original_message = await query.message.edit_text("Send keywords to filter (separated by a space).\n\n/cancel - to cancel")
      try:
          keyword_message = await bot.ask(user_id, text="Send your keywords now.", timeout=300)
          if keyword_message.text and keyword_message.text.lower() == '/cancel':
              return await handle_cancellation(original_message, keyword_message)

          keywords_to_add = keyword_message.text.lower().split(" ")
          current_keywords = (await get_configs(user_id))['keywords'] or []

          new_keywords = [kw for kw in keywords_to_add if kw not in current_keywords]
          updated_keywords = current_keywords + new_keywords

          await update_configs(user_id, 'keywords', updated_keywords)
          await keyword_message.delete()
          await original_message.edit_text("Keywords filter updated. ✓", reply_markup=InlineKeyboardMarkup(buttons))
      except asyncio.TimeoutError:
          await original_message.edit_text('Process timed out.', reply_markup=InlineKeyboardMarkup(buttons))


    elif type == "get_keyword":
      keywords = (await get_configs(user_id))['keywords']
      btn = extract_btn(keywords)
      btn.append([InlineKeyboardButton('+ Add', 'settings#add_keyword')])
      btn.append([InlineKeyboardButton('Remove All', 'settings#rmve_all_keyword')])
      btn.append([InlineKeyboardButton('« Back', 'settings#main')])
      await query.message.edit_text(
          text='<b>֎ Keyword Filter ֎</b>\n\nFiles with these keywords in the file name will be forwarded.',
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
