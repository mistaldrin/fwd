import re
import random
import time as tm
import logging
from uuid import uuid4
from database import db
from config import temp
from translation import Translation
from .test import parse_buttons
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

STATUS = {}
SYD = ["https://files.catbox.moe/3lwlbm.png"]
logger = logging.getLogger(__name__)

class STS:
    def __init__(self, id):
        self.id = id
        self.data = STATUS

    def verify(self):
        return self.data.get(self.id)

    def store(self, From, to, start_id, end_id):
        self.data[self.id] = {
            "FROM": From, 'TO': to, 'total_files': 0,
            'start_id': start_id, 'end_id': end_id,
            'fetched': 0, 'filtered': 0, 'deleted': 0,
            'duplicate': 0, 'total': abs(end_id - start_id) + 1, 'start': 0
        }
        self.get(full=True)
        return STS(self.id)

    def get(self, value=None, full=False):
        values = self.data.get(self.id)
        if not full:
           return values.get(value)
        for k, v in values.items():
            setattr(self, k, v)
        return self

    def add(self, key=None, value=1, time=False):
        if time:
          self.data[self.id].update({'start': tm.time()})
        self.data[self.id].update({key: self.get(key) + value})

    def divide(self, no, by):
       by = 1 if int(by) == 0 else by
       return int(no) / by

    async def get_data(self, user_id):
        bot_id = temp.FORWARD_BOT_ID.get(user_id)
        if not bot_id:
            raise ValueError("Bot ID not found in session.")

        bot = await db.get_bot(user_id, bot_id)
        k, filters = self, await db.get_filters(user_id)
        size, configs = None, await db.get_configs(user_id)
        if configs['duplicate']:
           duplicate = [configs['db_uri'], self.TO]
        else:
           duplicate = False
        button = parse_buttons(configs['button'] if configs['button'] else '')
        if configs['file_size'] != 0:
            size = [configs['file_size'], configs['size_limit']]

        return bot, configs['caption'], configs['forward_tag'], {
            'filters': filters, 'keywords': configs['keywords'],
            'media_size': size, 'extensions': configs['extension'],
            'skip_duplicate': duplicate
        }, configs['protect'], button

async def start_range_selection(bot, message, from_chat_id, from_title, to_chat_id, start_id, end_id):
    """Initiates an interactive message range selection process."""
    session_id = str(uuid4())
    temp.RANGE_SESSIONS[session_id] = {
        'user_id': message.chat.id,
        'chat_id': message.chat.id,
        'from_chat_id': from_chat_id,
        'from_title': from_title,
        'to_chat_id': to_chat_id,
        'start_id': start_id,
        'end_id': end_id,
        'order': 'asc' # Default order
    }
    await update_range_message(bot, session_id)

async def update_range_message(bot, session_id, message=None):
    """Edits or sends the range selection message."""
    session = temp.RANGE_SESSIONS.get(session_id)
    if not session: return

    order_text = "Oldest ➔ Newest" if session['order'] == 'asc' else "Newest ➔ Oldest"
    text = Translation.RANGE_SELECTION_TXT
    display_button_text = f"Range: {session['start_id']} ➔ {session['end_id']} ({order_text})"

    buttons = [
        [InlineKeyboardButton(display_button_text, callback_data="range_info")],
        [InlineKeyboardButton("✎ Edit Start", callback_data=f"range_edit_start_{session_id}"),
         InlineKeyboardButton("✎ Edit End", callback_data=f"range_edit_end_{session_id}")],
        [InlineKeyboardButton("⇄ Swap Order", callback_data=f"range_swap_{session_id}")],
        [InlineKeyboardButton("✓ Confirm Range", callback_data=f"range_confirm_{session_id}")],
        [InlineKeyboardButton("« Cancel", callback_data=f"range_cancel_{session_id}")]
    ]

    reply_markup = InlineKeyboardMarkup(buttons)
    try:
        # Use the correct message object to send the photo
        await bot.send_photo(chat_id=session['chat_id'], photo=random.choice(SYD),
                             caption=text, reply_markup=reply_markup, quote=True)
    except Exception as e:
        logger.error(f"Error sending range message: {e}", exc_info=True)
