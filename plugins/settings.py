# mistaldrin/fwd/fwd-dawn-improve-v2/plugins/settings.py
import asyncio
import random
from database import db
from config import Config, temp
from translation import Translation
from pyrogram import Client, filters
from .test import get_configs, update_configs, CLIENT
from .utils import parse_buttons
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

CLIENT = CLIENT()
SYD = ["https://files.catbox.moe/3lwlbm.png"]


@Client.on_message(filters.private & filters.command(['settings']))
async def settings(client, message):
    user_id = message.from_user.id
    if temp.lock.get(user_id):
        return await message.reply("A task is already in progress. Please wait for it to complete before changing settings.")

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
    await query.answer()
    user_id = query.from_user.id

    if temp.lock.get(user_id):
        return await query.answer("A task is already in progress. Please wait for it to complete before changing settings.", show_alert=True)

    try:
        parts = query.data.split("#")
        type = parts[1]
        data = parts[2] if len(parts) > 2 else None

        if type == "main":
            await query.message.edit_text(
                "<b>֎ Settings ֎</b>\n\nManage personal configurations.",
                reply_markup=main_buttons()
            )

        elif type in ["caption", "button", "db_uri", "file_size", "size_limit", "extension", "keywords"]:
            # These settings require text input
            prompt_text = {
                "caption": "Send your custom caption. Use placeholders like `{filename}`, `{size}`, and `{caption}`.",
                "button": "Send your button in the format: `[Button Text][buttonurl:https://example.com]`",
                "db_uri": "Send your MongoDB connection string to be used for duplicate checking.",
                "file_size": "Send the file size limit in MB.",
                "size_limit": "Choose whether to allow files 'above' or 'below' the size limit.",
                "extension": "Send a comma-separated list of file extensions to filter (e.g., `mkv,mp4,zip`).",
                "keywords": "Send a comma-separated list of keywords to filter. Use a `-` prefix to exclude messages with a keyword (e.g., `cat,-dog`)."
            }
            await query.message.delete()
            prompt = await bot.send_message(user_id, prompt_text[type] + "\n\n/cancel to abort. /reset to clear this setting.")
            temp.USER_STATES[user_id] = {
                "state": f"awaiting_{type}",
                "prompt_message_id": prompt.id
            }

        elif type == "filters":
            await query.message.edit_text(
                "<b>֎ Message Filters ֎</b>\n\nToggle which message types to forward.",
                reply_markup=await get_filters_markup(user_id)
            )

        elif type == "toggle_filter":
            filter_key = data
            current_configs = await get_configs(user_id)
            current_filters = current_configs.get('filters', {})
            current_filters[filter_key] = not current_filters.get(filter_key, True)
            await update_configs(user_id, 'filters', current_filters)
            await query.message.edit_reply_markup(reply_markup=await get_filters_markup(user_id))


        # Other settings logic...
        elif type == "bots":
            buttons = []
            bots = await db.get_bots(user_id)
            for _bot in bots:
                if not _bot.get('id'): continue
                bot_name = _bot.get('name') or _bot.get('username', f"ID: {_bot['id']}")
                bot_id = _bot.get('id')
                buttons.append([InlineKeyboardButton(bot_name, callback_data=f"settings#editbot#{bot_id}")])
            buttons.append([InlineKeyboardButton('+ Add Bot', callback_data="settings#addbot")])
            buttons.append([InlineKeyboardButton('+ Add Userbot', callback_data="settings#adduserbot")])
            buttons.append([InlineKeyboardButton('« Back', callback_data="settings#main")])
            await query.message.edit_text(
                "<b>֎ Bots & Userbots ֎</b>\n\nManage connected bots and userbots.",
                reply_markup=InlineKeyboardMarkup(buttons)
            )

        # ... (rest of the settings logic for bots and channels)

    except Exception as e:
        logger.error(f"Error in settings_query: {e}", exc_info=True)
        # Safe error reporting
        try:
            await query.message.reply_text("An unexpected error occurred. Please try again later.")
        except:
            await bot.send_message(user_id, "An unexpected error occurred. Please try again later.")

@Client.on_message(filters.private & filters.incoming, group=-1)
async def settings_input_handler(bot: Client, message: Message):
    user_id = message.from_user.id
    state_info = temp.USER_STATES.get(user_id)

    if not state_info or not state_info.get("state", "").startswith("awaiting_"):
        return

    state = state_info["state"].split("_", 1)[1]
    prompt_id = state_info.get("prompt_message_id")

    # Clean up prompt and user message
    try:
        if prompt_id: await bot.delete_messages(user_id, prompt_id)
        await message.delete()
    except Exception:
        pass

    temp.USER_STATES.pop(user_id, None)

    if message.text.lower() == "/cancel":
        return await bot.send_message(user_id, "Cancelled.")

    value = None
    if message.text.lower() == "/reset":
        value = None # This will clear the setting
    elif state == "file_size":
        try:
            value = float(message.text) * 1024 * 1024 # Convert MB to bytes
        except ValueError:
            return await bot.send_message(user_id, "Invalid number for file size.")
    elif state == "size_limit":
        if message.text.lower() not in ["above", "below"]:
            return await bot.send_message(user_id, "Invalid option. Please enter 'above' or 'below'.")
        value = message.text.lower()
    else:
        value = message.text

    await update_configs(user_id, state, value)
    await bot.send_message(user_id, f"✅ **{state.replace('_', ' ').title()}** has been updated.")


async def get_filters_markup(user_id):
    configs = await get_configs(user_id)
    filters = configs.get('filters', {})
    buttons = []
    filter_keys = ['text', 'photo', 'video', 'document', 'audio', 'voice', 'sticker', 'animation', 'poll']
    for key in filter_keys:
        status = "✓" if filters.get(key, True) else "✗"
        buttons.append(InlineKeyboardButton(f"{status} {key.title()}", callback_data=f"settings#toggle_filter#{key}"))
    
    # Arrange buttons in rows of 2
    markup = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    markup.append([InlineKeyboardButton('« Back', callback_data="settings#main")])
    return InlineKeyboardMarkup(markup)


def main_buttons():
    buttons = [[
        InlineKeyboardButton('Bots & Userbots', callback_data=f'settings#bots'),
        InlineKeyboardButton('Channels', callback_data=f'settings#channels')
    ], [
        InlineKeyboardButton('Caption', callback_data=f'settings#caption'),
        InlineKeyboardButton('Button', callback_data=f'settings#button')
    ], [
        InlineKeyboardButton('Message Filters', callback_data=f'settings#filters'),
        InlineKeyboardButton('File Size Filter', callback_data=f'settings#file_size')
    ], [
        InlineKeyboardButton('Keyword Filter', callback_data=f'settings#keywords'),
        InlineKeyboardButton('Extension Filter', callback_data=f'settings#extension')
    ], [
        InlineKeyboardButton('Duplicate Check DB', callback_data=f'settings#db_uri')
    ],[
        InlineKeyboardButton('« Back', callback_data='back')
    ]]
    return InlineKeyboardMarkup(buttons)
