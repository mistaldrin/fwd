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
        InlineKeyboardButton('Help', callback_data='help'),
        InlineKeyboardButton('About', callback_data='about')
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


#===================Reset Me Function===================#

@Client.on_message(filters.private & filters.command(['resetme']))
async def reset_user(client, message):
    user_id = message.from_user.id
    
    # Confirmation prompt
    await message.reply_text(
        "**⚠️ Are you sure?**\n\nThis will delete all your saved bots, userbots, and channel configurations. This action cannot be undone.",
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("✅ Yes, I am sure", callback_data="confirm_reset")],
                [InlineKeyboardButton("❌ Cancel", callback_data="close_btn")]
            ]
        )
    )

@Client.on_callback_query(filters.regex(r'^confirm_reset'))
async def confirm_reset_callback(bot, query):
    user_id = query.from_user.id
    try:
        await db.reset_user_data(user_id)
        await query.message.edit_text("✅ **Your account has been successfully reset.**\n\nPlease use /start to begin again.")
    except Exception as e:
        await query.message.edit_text(f"An error occurred during reset: `{e}`")


#==================Restart Function==================#

@Client.on_message(filters.private & filters.command(['restart', "r"]) & filters.user(Config.OWNER_ID))
async def restart(client, message):
    msg = await message.reply_text(
        text="<i>Restarting...</i>",
        quote=True
    )
    await asyncio.sleep(2)
    await msg.edit("<i>Successfully restarted.</i>")
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
            InlineKeyboardButton('How to Use', callback_data='how_to_use')
            ],[
            InlineKeyboardButton('Settings', callback_data='settings#main'),
            InlineKeyboardButton('Stats', callback_data='status')
            ],[
            InlineKeyboardButton('« Back', callback_data='back')
            ]]
        ))

@Client.on_message(filters.private & filters.command(["forwardelay", "fd"]))
async def forward_delay(client, message):
    user_id = message.from_user.id
    
    # Explicitly check if the user is banned
    ban_status = await db.get_ban_status(user_id)
    if ban_status["is_banned"]:
        return await message.reply_text(f"You are banned from using this bot.\n\nReason: {ban_status['ban_reason']}")

    if len(message.command) < 2:
        return await message.reply_text(Translation.FORWARDELAY_TXT)
    
    try:
        delay = float(message.command[1])
        if delay < 0:
            return await message.reply_text("The delay must be a positive number.")
        
        await update_configs(user_id, 'forward_delay', delay)
        await message.reply_text(f"Forwarding delay set to `{delay}` seconds.")
    except ValueError:
        await message.reply_text("Invalid input. Please provide a number.")


@Client.on_callback_query(filters.regex(r'^how_to_use'))
async def how_to_use(bot, query):
    await query.message.edit_text(
        text=Translation.HOW_USE_TXT,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('« Back', callback_data='help')]]),
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
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('« Back', callback_data='back')]]),
        disable_web_page_preview=True,
        parse_mode=enums.ParseMode.HTML,
    )



@Client.on_callback_query(filters.regex(r'^status'))
async def status(bot, query):
    users_count, bots_count = await db.total_users_bots_count()
    await query.message.edit_text(
        text=Translation.STATUS_TXT.format(users_count, bots_count, temp.forwardings),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('« Back', callback_data='help')]]),
        parse_mode=enums.ParseMode.HTML,
        disable_web_page_preview=True,
    )
