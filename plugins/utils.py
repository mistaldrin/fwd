import re
import time as tm
from database import db 
from config import temp
from uuid import uuid4
from translation import Translation
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

STATUS = {}
SYD = ["https://files.catbox.moe/3lwlbm.png"]

def parse_buttons(text, markup=True):
    BTN_URL_REGEX = re.compile(r"(\[([^\[]+?)]\[buttonurl:/{0,2}(.+?)(:same)?])")
    buttons = []
    if not text: return None
    for match in BTN_URL_REGEX.finditer(text):
        n_escapes = 0
        to_check = match.start(1) - 1
        while to_check > 0 and text[to_check] == "\\":
            n_escapes += 1
            to_check -= 1

        if n_escapes % 2 == 0:
            if bool(match.group(4)) and buttons:
                buttons[-1].append(InlineKeyboardButton(text=match.group(2), url=match.group(3).replace(" ", "")))
            else:
                buttons.append([InlineKeyboardButton(text=match.group(2), url=match.group(3).replace(" ", ""))])
    if markup and buttons:
       buttons = InlineKeyboardMarkup(buttons)
    return buttons if buttons else None


class STS:
    def __init__(self, id):
        self.id = id
        self.data = STATUS
    
    def verify(self):
        return self.data.get(self.id)
    
    def store(self, From, to, skip, limit):
        self.data[self.id] = {"FROM": From, 'TO': to, 'total_files': 0, 'skip': skip, 'limit': limit,
                      'fetched': 0, 'filtered': 0, 'deleted': 0, 'duplicate': 0, 'total': abs(limit-skip), 'start': 0}
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
          return self.data[self.id].update({'start': tm.time()})
        self.data[self.id].update({key: self.get(key) + value}) 
    
    def divide(self, no, by):
       by = 1 if int(by) == 0 else by 
       return int(no) / by 
    
    async def get_data(self, user_id, bot_id):
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
        return bot, configs['caption'], configs['forward_tag'], {'chat_id': k.FROM, 'limit': k.limit, 'offset': k.skip, 'filters': filters,
                'keywords': configs['keywords'], 'media_size': size, 'extensions': configs['extension'], 'skip_duplicate': duplicate}, configs['protect'], button
        

def get_readable_time(seconds: int) -> str:
    result = ""
    (days, remainder) = divmod(seconds, 86400)
    days = int(days)
    if days != 0:
        result += f"{days}d"
    (hours, remainder) = divmod(remainder, 3600)
    hours = int(hours)
    if hours != 0:
        result += f"{hours}h"
    (minutes, seconds) = divmod(remainder, 60)
    minutes = int(minutes)
    if minutes != 0:
        result += f"{minutes}m"
    seconds = int(seconds)
    result += f"{seconds}s"
    return result

async def start_range_selection(bot, user_id, chat_id, from_chat_id, from_title, to_chat_id, last_msg_id, final_callback_prefix):
    session_id = str(uuid4())
    temp.RANGE_SESSIONS[session_id] = {
        'user_id': user_id, 'chat_id': chat_id, 'from_chat_id': from_chat_id,
        'from_title': from_title, 'to_chat_id': to_chat_id, 'start_id': 1,
        'end_id': last_msg_id, 'order': 'asc', 'final_callback': final_callback_prefix,
        'last_msg_id': last_msg_id
    }
    await update_range_message(bot, session_id)

async def update_range_message(bot, session_id, message=None):
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
        [InlineKeyboardButton("✓ Confirm Custom Range", callback_data=f"range_confirm_{session_id}")],
        [InlineKeyboardButton("🚀 Forward All", callback_data=f"range_all_{session_id}")],
        [InlineKeyboardButton("« Cancel", callback_data=f"range_cancel_{session_id}")]
    ]
    
    reply_markup = InlineKeyboardMarkup(buttons)
    try:
        if message:
            await message.edit_caption(caption=text, reply_markup=reply_markup)
        else:
            await bot.send_photo(chat_id=session['chat_id'], photo=random.choice(SYD),
                                 caption=text, reply_markup=reply_markup, quote=True)
    except Exception as e:
        print(f"Error updating range message: {e}")
