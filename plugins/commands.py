import os
import sys
import asyncio 
import random
from database import db, mongodb_version
from config import Config, temp
from platform import python_version
from translation import Translation
from pyrogram import Client, filters, enums, __version__ as pyrogram_version
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaDocument
from .test import update_configs

SYD = ["https://files.catbox.moe/mq4f9j.jpg", "https://files.catbox.moe/mq4f9j.jpg"]

main_buttons = [[
        InlineKeyboardButton('⊛ Hᴇʟᴩ ⊛', callback_data='help'),
        InlineKeyboardButton('✧ Aʙᴏᴜᴛ ✧', callback_data='about')
]]



#===================Start Function===================#

@Client.on_message(filters.private & filters.command(['start']))
async def start(client, message):
    user = message.from_user
    try:
        if not await db.is_user_exist(user.id):
            await db.add_user(user.id, user.first_name)
    except Exception as e:
        print(f"Error in user registration: {e}")

    reply_markup = InlineKeyboardMarkup(main_buttons)
    text=Translation.START_TXT.format(user.mention)
    await message.reply_photo(
        photo=random.choice(SYD),
        caption=text,
        reply_markup=reply_markup
    )



#==================Restart Function==================#

@Client.on_message(filters.private & filters.command(['restart', "r"]) & filters.user(Config.OWNER_ID))
async def restart(client, message):
    msg = await message.reply_text(
        text="<i>Trying To Restarting.....</i>",
        quote=True
    )
    await asyncio.sleep(5)
    await msg.edit("<i>Successfully Restarted</i>")
    os.execl(sys.executable, sys.executable, *sys.argv)
    
@Client.on_message(filters.command("start") & filters.chat(-1002687879857))
async def sydstart(client, message):
    await message.reply_text(".")

#==================Callback Functions==================#

@Client.on_callback_query(filters.regex(r'^help'))
async def helpcb(bot, query):
    await query.message.edit_text(
        text=Translation.HELP_TXT,
        reply_markup=InlineKeyboardMarkup(
            [[
            InlineKeyboardButton('∿ Hᴏᴡ To Uꜱᴇ Mᴇ ∿', callback_data='how_to_use')
            ],[
            InlineKeyboardButton('⛭ SᴇᴛᴛɪɴGS ⛭', callback_data='settings#main'),
            InlineKeyboardButton('∗ SᴛᴀᴛS ∗', callback_data='status')
            ],[
            InlineKeyboardButton('⇇ Bᴀᴄᴋ', callback_data='back')
            ]]
        ))

@Client.on_message(filters.private & filters.command(["forwardelay", "fd"]))
async def forward_delay(client, message):
    if len(message.command) < 2:
        return await message.reply_text(Translation.FORWARDELAY_TXT)
    
    try:
        delay = float(message.command[1])
        if delay < 0:
            return await message.reply_text("The delay must be a positive number.")
        
        user_id = message.from_user.id
        await update_configs(user_id, 'forward_delay', delay)
        await message.reply_text(f"Forwarding delay set to {delay} seconds.")
    except ValueError:
        await message.reply_text("Invalid input. Please provide a number.")


@Client.on_callback_query(filters.regex(r'^how_to_use'))
async def how_to_use(bot, query):
    await query.message.edit_text(
        text=Translation.HOW_USE_TXT,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('⇇ Bᴀᴄᴋ', callback_data='help')]]),
        disable_web_page_preview=True
    )



@Client.on_callback_query(filters.regex(r'^back'))
async def back(bot, query):
    reply_markup = InlineKeyboardMarkup(main_buttons)
    await query.message.edit_text(
       reply_markup=reply_markup,
       text=Translation.START_TXT.format(
                query.from_user.first_name))



@Client.on_callback_query(filters.regex(r'^about'))
async def about(bot, query):
    await query.message.edit_text(
        text=Translation.ABOUT_TXT.format(bot.me.mention),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('⇇ Bᴀᴄᴋ', callback_data='back')]]),
        disable_web_page_preview=True,
        parse_mode=enums.ParseMode.HTML,
    )



@Client.on_callback_query(filters.regex(r'^status'))
async def status(bot, query):
    users_count, bots_count = await db.total_users_bots_count()
    await query.message.edit_text(
        text=Translation.STATUS_TXT.format(users_count, bots_count, temp.forwardings),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('⇇ Bᴀᴄᴋ', callback_data='help')]]),
        parse_mode=enums.ParseMode.HTML,
        disable_web_page_preview=True,
    )
