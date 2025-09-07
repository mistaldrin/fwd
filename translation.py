import os
from config import Config

class Translation(object):
  START_TXT = """Hello there, {}.

A personal assistant for message forwarding.

Select 'Help' for a list of commands.
(o･ω･o)"""


  HELP_TXT = """<b>֎ Help Menu ֎</b>

Available commands:

● /start - Check if alive.
● /forward - Forward messages from a chat.
● /settings - Open the configuration menu.
● /resetme - A fresh start. Wipes all settings.
"""
  
  HOW_USE_TXT = """<b>֎ How to Use ֎</b>

A quick checklist to get started:

1.  <b>Add Bot/Userbot:</b> Add a bot token or userbot session in /settings.
2.  <b>Add Channels:</b> Add target channels where your bot/userbot is an admin.
3.  <b>Check Permissions:</b>
    - Userbot must be in the source channel if it's private.
    - Bot/userbot needs admin rights in the target channel.

Ready? Use /forward to begin. (ﾉ´ヮ`)ﾉ*:･ﾟ✧"""
  
  ABOUT_TXT = """<b>֎ About ֎</b>

● <b>Name:</b> {}
● <b>Language:</b> Python
● <b>Library:</b> Pyrogram
● <b>Developer:</b> <a href='https://t.me/partDevil'>partDevil</a>"""
  
  STATUS_TXT = """<b>֎ Bot Status ֎</b>
  
● <b>Total Users:</b> <code>{}</code>
● <b>Total Bots & Userbots:</b> <code>{}</code>
● <b>Active Forwards:</b> <code>{}</code>
"""
  
  TO_MSG = "<b><u>Choose Target Chat</u></b>\n\nChoose your target chat from the given buttons.\n\n/cancel - To cancel this process."
  FROM_MSG = "<b><u>Set End Point</u></b>\n\nForward the <b>last message</b> you want to include in the range, or send a link to it.\n\n/cancel - To cancel."
  START_MSG = "<b><u>Set Start Point</u></b>\n\nNow, forward the <b>first message</b> you want to include in the range, or send a link to it.\n\n/cancel - To cancel."

  RANGE_SELECTION_TXT = """<b>֎ Message Range ֎</b>

Your range is set. You can confirm to start forwarding, or use the buttons to make adjustments.

<i>Note: Large channels can take a while. Patience is a virtue.</i>"""
  
  CANCEL = "Process cancelled successfully!"
  BOT_DETAILS = "<b><u>Bot Details</u></b>\n\n<b>Name:</b> <code>{}</code>\n<b>Bot ID:</b> <code>{}</code>\n<b>Username:</b> @{}"
  USER_DETAILS = "<b><u>Userbot Details</u></b>\n\n<b>Name:</b> <code>{}</code>\n<b>User ID:</b> <code>{}</code>\n<b>Username:</b> @{}"  
         
  TEXT = """<b><u>Forwarding Status</u></b>
  
<b>Fetched:</b> <code>{fetched}</code> of <code>{total}</code>
<b>Forwarded:</b> <code>{forwarded}</code>
<b>Duplicate:</b> <code>{duplicate}</code>
<b>Deleted/Skipped:</b> <code>{deleted}</code>
<b>Status:</b> <code>{status}</code>
<b>Progress:</b> <code>{percentage}</code>%

{progress_bar}
"""

  DOUBLE_CHECK = """<b><u>Final Check</u></b>
  
Please confirm the final details:

● <b>Your Bot/Userbot:</b> [{botname}](t.me/{botuname})
● <b>From Channel:</b> <code>{from_chat}</code>
● <b>To Channel:</b> <code>{to_chat}</code>
● <b>Message Range:</b> <code>{message_range}</code>

<i>Make sure [{botname}](t.me/{botuname}) is an admin in the <b>Target Channel</b> (<code>{to_chat}</code>).</i>

<b>Proceed?</b>"""
