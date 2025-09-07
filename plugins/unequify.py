import os
import asyncio
import io
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import FloodWait, ChannelInvalid, UsernameNotOccupied, UsernameInvalid, PeerIdInvalid, UserAlreadyParticipant

from .test import CLIENT
from .utils import start_range_selection, force_subscribe
from translation import Translation
from config import temp
from database import db

# --- Constants for the interactive menu ---
OPTION_LABELS = ["Text", "Photos/Videos", "Audio", "Documents", "Stickers"]
DEFAULT_STATE = "01010"

def create_selection_keyboard(selection_state: str, session_id: str) -> InlineKeyboardMarkup:
    """Creates the interactive keyboard for selecting message types."""
    buttons = []
    state_list = list(selection_state)

    for i, label in enumerate(OPTION_LABELS):
        text = f"✅ {label}" if state_list[i] == '1' else label
        callback_data = f"uneq_toggle_{selection_state}_{i}_{session_id}"
        buttons.append([InlineKeyboardButton(text, callback_data=callback_data)])

    buttons.append([
        InlineKeyboardButton("🚀 Start Scan", callback_data=f"uneq_startscan_{selection_state}_{session_id}"),
        InlineKeyboardButton("❌ Cancel", callback_data=f"range_cancel_{session_id}")
    ])
    return InlineKeyboardMarkup(buttons)

@Client.on_message(filters.command("unequify") & filters.private)
@force_subscribe
async def unequify_start(bot: Client, message: Message):
    """
    Initial entry point for the /unequify command.
    """
    user_id = message.from_user.id
    userbots = [b for b in await db.get_bots(user_id) if not b.get('is_bot')]

    if not userbots:
        await message.reply_text("❌ **Userbot Not Found!**\n\nPlease add a Userbot session via the /settings menu to use this feature.")
        return

    if len(userbots) > 1:
        buttons = []
        for ub in userbots:
            buttons.append([InlineKeyboardButton(ub['name'], callback_data=f"uneq_select_userbot_{ub['id']}")])
        buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="close_btn")])
        await message.reply_text("<b><u>Select a Userbot</u></b>\n\nChoose the userbot you want to use for deduplication.", reply_markup=InlineKeyboardMarkup(buttons))
        return
    
    await unequify_continue(bot, message, userbots[0]['id'])

@Client.on_callback_query(filters.regex("^uneq_select_userbot_"))
async def select_userbot_unequify(bot: Client, query: CallbackQuery):
    userbot_id = int(query.data.split('_')[-1])
    await query.message.delete()
    await unequify_continue(bot, query.message, userbot_id)

async def unequify_continue(bot: Client, message: Message, userbot_id: int):
    user_id = message.from_user.id
    # Use the per-user session dictionary
    temp.UNEQUIFY_USERBOT_ID[user_id] = userbot_id

    if len(message.command) < 2:
        # Show interactive menu if no target is provided
        buttons = [
            [InlineKeyboardButton("Manual Input", callback_data="uneq_manual")],
            [InlineKeyboardButton("Select from Userbot Chats", callback_data="uneq_select_from_userbot")]
        ]
        await message.reply_text(Translation.UNEQUIFY_START_TXT, reply_markup=InlineKeyboardMarkup(buttons))
        return

    target_channel_input = message.command[1]

    # A target was provided, so start the range selection process directly
    try:
        # Use the selected userbot to get chat info, not the main bot
        userbot_config = await db.get_bot(user_id, userbot_id)
        if not userbot_config:
            return await message.reply("Could not find the selected userbot's configuration.")

        async with CLIENT().client(userbot_config) as temp_client:
            chat = await temp_client.get_chat(target_channel_input)
            last_msg_id = 0
            async for last_message in temp_client.get_chat_history(chat.id, limit=1):
                last_msg_id = last_message.id
                break
            await start_range_selection(bot, message, from_chat_id=chat.id, from_title=chat.title, to_chat_id=None, last_msg_id=last_msg_id, final_callback_prefix="uneq_final")

    except (UsernameInvalid, PeerIdInvalid, ChannelInvalid) as e:
        await message.reply(f"Could not find the chat: `{e}`. Please check the username/ID.")
    except Exception as e:
        await message.reply(f"An error occurred: {e}")


@Client.on_message(filters.command("ubclist") & filters.private)
@force_subscribe
async def get_userbot_chat_list(bot: Client, message: Message):
    user_id = message.from_user.id
    userbots = [b for b in await db.get_bots(user_id) if not b.get('is_bot')]
    
    if not userbots:
        await message.reply_text("❌ **Userbot Not Found!**\n\nPlease add a Userbot session via the /settings menu to use this feature.")
        return

    if len(userbots) > 1:
        buttons = []
        for ub in userbots:
            buttons.append([InlineKeyboardButton(ub['name'], callback_data=f"ubclist_select_{ub['id']}")])
        buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="close_btn")])
        await message.reply_text("<b><u>Select a Userbot</u></b>\n\nChoose the userbot whose chat list you want to see.", reply_markup=InlineKeyboardMarkup(buttons))
        return
        
    await list_userbot_chats(bot, message, userbots[0]['id'])

@Client.on_callback_query(filters.regex("^ubclist_select_"))
async def select_userbot_ubclist(bot: Client, query: CallbackQuery):
    userbot_id = int(query.data.split('_')[-1])
    await query.message.delete()
    await list_userbot_chats(bot, query.message, userbot_id)

async def list_userbot_chats(bot: Client, message: Message, userbot_id: int):
    user_id = message.from_user.id
    userbot_config = await db.get_bot(user_id, userbot_id)

    sts = await message.reply("`Fetching chat list from userbot... This might take a while.`")

    chat_list_text = "Userbot Chat List\n\n"
    chat_list_text += "Format: [Permission] Chat Title - `Chat ID`\n\n"

    try:
        session_string = userbot_config['session']
        # Use the async with context manager to handle start/stop automatically
        async with CLIENT().client(session_string, user=True) as userbot:
            async for dialog in userbot.get_dialogs():
                chat = dialog.chat
                perms = "❌"
                try:
                    me = await userbot.get_chat_member(chat.id, "me")
                    if me.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
                       perms = "✅"
                except Exception:
                    pass

                chat_list_text += f"{perms} {chat.title} - `{chat.id}`\n"

        # Send as a text file if too long, otherwise as a message
        if len(chat_list_text) > 4096:
            with io.StringIO(chat_list_text) as file:
                file.name = "userbot_chats.txt"
                await message.reply_document(file, caption="Here is the list of chats accessible by your userbot.")
        else:
            await message.reply_text(chat_list_text)
        await sts.delete()

    except Exception as e:
        await sts.edit(f"❌ **An error occurred while fetching chats.**\n\n`{e}`")


@Client.on_callback_query(filters.regex("^uneq_"))
async def unequify_callbacks(bot: Client, query: CallbackQuery):
    user_id = query.from_user.id
    data = query.data.split("_", 1)[1]

    if data == "manual":
        await query.answer()
        try:
            ask_msg = await bot.ask(query.message.chat.id, "Please send the channel username or ID.", timeout=60)
            target = ask_msg.text
            await query.message.delete()
            # Re-call the main function with the provided target
            msg_copy = query.message
            msg_copy.from_user = query.from_user # Important for context
            msg_copy.text = f"/unequify {target}"
            msg_copy.command = ["unequify", target]
            await unequify_start(bot, msg_copy)
        except asyncio.TimeoutError:
            await query.message.edit_text("Cancelled.")

    elif data == "select_from_userbot":
        # Get the userbot_id from the user-specific session
        userbot_id = temp.UNEQUIFY_USERBOT_ID.get(user_id)
        if not userbot_id:
            return await query.message.edit("Error: Could not determine which userbot to use. Please start over.")

        userbot_config = await db.get_bot(user_id, userbot_id)
        if not userbot_config or not userbot_config.get('session'):
            return await query.message.edit("Userbot not found. Please add one in /settings.")

        await query.message.edit("`Fetching chats... This may take a moment.`")

        chats = {}
        serial = 1
        text = "Reply with the Serial Number (S.No) or the Chat ID of the target channel.\n\n"
        try:
            session_string = userbot_config['session']
            async with CLIENT().client(session_string, user=True) as userbot:
                async for dialog in userbot.get_dialogs():
                    chats[str(serial)] = dialog.chat
                    chats[str(dialog.chat.id)] = dialog.chat
                    text += f"**{serial}.** {dialog.chat.title} (`{dialog.chat.id}`)\n"
                    serial += 1

            await query.message.edit(text)

            try:
                reply = await bot.listen(chat_id=query.message.chat.id, user_id=query.from_user.id, timeout=120)
                selected_chat = chats.get(reply.text.strip())

                if not selected_chat:
                    return await query.message.reply_text("Invalid selection. Please start over.")

                await query.message.delete()
                last_msg_id = 0
                async for last_message in userbot.get_chat_history(selected_chat.id, limit=1):
                    last_msg_id = last_message.id
                    break
                # Start range selection for the chosen chat
                await start_range_selection(bot, query, from_chat_id=selected_chat.id, from_title=selected_chat.title, to_chat_id=None, last_msg_id=last_msg_id, final_callback_prefix="uneq_final")

            except asyncio.TimeoutError:
                await query.message.reply_text("Selection timed out.")

        except Exception as e:
            await query.message.edit(f"An error occurred: `{e}`")

    elif data.startswith("types_"):
        _, session_id = data.split("_", 1)
        keyboard = create_selection_keyboard(DEFAULT_STATE, session_id)
        await query.message.edit_text(
            "**Select Message Types**\n\nPlease select the types of messages you wish to find duplicates of.",
            reply_markup=keyboard
        )

    elif data.startswith("toggle_"):
        _, current_state, index_str, session_id = data.split("_", 3)
        index = int(index_str)

        state_list = list(current_state)
        state_list[index] = '1' if state_list[index] == '0' else '0'
        new__state = "".join(state_list)

        new_keyboard = create_selection_keyboard(new_state, session_id)
        await query.message.edit_reply_markup(new_keyboard)
        await query.answer()

    elif data.startswith("startscan_"):
        await query.message.edit_text("`Processing...`", reply_markup=None)
        _, selection_state, session_id = data.split("_", 2)
        await start_deduplication(bot, query, selection_state, session_id)


async def start_deduplication(bot: Client, callback_query: CallbackQuery, selection_state: str, session_id: str):
    status_message = callback_query.message
    user_id = callback_query.from_user.id
    
    range_session = temp.RANGE_SESSIONS.pop(session_id, None)
    if not range_session:
        return await status_message.edit_text("Error: Session expired or invalid.")

    # Get userbot_id from the user-specific session
    userbot_id = temp.UNEQUIFY_USERBOT_ID.pop(user_id, None)
    if not userbot_id:
        return await status_message.edit_text("Error: Could not determine which userbot to use. Please start over.")

    userbot_config = await db.get_bot(user_id, userbot_id)
    if not userbot_config or not userbot_config.get('session'):
        return await status_message.edit_text("Error: Userbot not found.")

    target_channel = range_session['from_chat_id']
    start_id = min(range_session['start_id'], range_session['end_id'])
    end_id = max(range_session['start_id'], range_session['end_id'])

    selections = [OPTION_LABELS[i] for i, bit in enumerate(selection_state) if bit == '1']
    if not selections:
        return await status_message.edit_text("❌ **No types selected!** Operation cancelled.")

    await status_message.edit_text(f"`Initializing userbot session...\n\nTargeting: {', '.join(selections)}`")

    seen_identifiers = set()
    duplicates_to_delete = []
    total_scanned = 0
    total_deleted = 0
    total_in_range = abs(end_id - start_id) + 1

    try:
        session_string = userbot_config['session']
        async with CLIENT().client(session_string, user=True) as userbot:
            chat = await userbot.get_chat(target_channel)

            await status_message.edit_text(f"`Accessing: {chat.title}`\n\n`Checking permissions...`")
            member = await userbot.get_chat_member(chat.id, "me")

            is_admin = member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
            can_delete = member.privileges and member.privileges.can_delete_messages if is_admin else False

            if not (is_admin and can_delete):
                return await status_message.edit_text(f"❌ **Permission Denied in '{chat.title}'!** You must be an admin with delete rights.")

            await status_message.edit_text(f"✅ **Permissions Confirmed!**\n\n`Starting scan...`")

            message_ids_to_scan = list(range(start_id, end_id + 1))

            for i in range(0, len(message_ids_to_scan), 200): # Use 200 batch size for get_messages
                chunk = message_ids_to_scan[i:i+200]
                messages = await userbot.get_messages(chat.id, chunk)

                for msg in messages:
                    if not msg: continue
                    total_scanned += 1
                    identifier = None

                    if selection_state[0] == '1' and msg.text:
                        identifier = msg.text.strip()
                    elif selection_state[1] == '1' and (msg.photo or msg.video) and hasattr(msg, 'media') and msg.media:
                        media_obj = getattr(msg, msg.media.value, None)
                        if media_obj: identifier = getattr(media_obj, 'file_unique_id', None)
                    elif selection_state[2] == '1' and msg.audio:
                        identifier = msg.audio.file_unique_id
                    elif selection_state[3] == '1' and msg.document:
                        identifier = msg.document.file_unique_id
                    elif selection_state[4] == '1' and msg.sticker:
                        identifier = msg.sticker.file_unique_id

                    if identifier and identifier in seen_identifiers:
                        duplicates_to_delete.append(msg.id)
                    elif identifier:
                        seen_identifiers.add(identifier)

                if len(duplicates_to_delete) >= 100:
                    await userbot.delete_messages(chat_id=chat.id, message_ids=duplicates_to_delete)
                    total_deleted += len(duplicates_to_delete)
                    duplicates_to_delete.clear()
                    progress_text = Translation.DUPLICATE_TEXT.format(total=total_in_range, scanned=total_scanned, deleted=total_deleted, progress="...")
                    try:
                        await status_message.edit_text(progress_text)
                    except FloodWait:
                        pass
                    await asyncio.sleep(5)

            if duplicates_to_delete:
                await userbot.delete_messages(chat_id=chat.id, message_ids=duplicates_to_delete)
                total_deleted += len(duplicates_to_delete)

            await status_message.edit_text(
                f"✅ **Deduplication Complete!**\n\n"
                f"**Chat:** {chat.title}\n"
                f"**Messages Scanned:** `{total_scanned}`\n"
                f"**Duplicates Deleted:** `{total_deleted}`"
            )

    except FloodWait as e:
        await status_message.edit_text(f"❌ **Rate Limit Exceeded.** Please wait `{e.value}` seconds.")
    except Exception as e:
        await status_message.edit_text(f"❌ **An unexpected error occurred.**\n\n`{e}`")
