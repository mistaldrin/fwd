#1
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
● /forward - Forward a range of messages.
● /unequify - Remove duplicates from a chat.
● /tasks - View and manage active tasks.
● /ubclist - List all userbot chats.
● /settings - Open the configuration menu.
● /resetme - A fresh start. Wipes all settings.
● /forwardelay - Set a custom forward delay.

<b>Features:</b>
▸ Custom message ranges.
▸ Interactive chat selection.
▸ Forwards from public & private channels.
▸ Custom captions & buttons.
▸ Skips duplicates automatically.
"""
  
  HOW_USE_TXT = """<b>֎ How to Use ֎</b>

A quick checklist to get started:

1.  <b>Add Bot/Userbot:</b> Add a bot token or userbot session in /settings.
2.  <b>Add Channels:</b> Add target channels where the bot/userbot is an admin.
3.  <b>Check Permissions:</b>
    - Userbot must be in private source channels.
    - Bot/userbot needs admin rights in target channels.

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
  
  FROM_MSG = "<b>Source Chat?</b>\n\nTo set the range, forward the <b>last message</b> you want to forward from the source chat, or send its link.\n\nThe range will start from the beginning (message 1) by default.\n\n/cancel - Abort mission."
  TO_MSG = "<b>Target Chat?</b>\n\nSelect a target chat from the buttons below.\n\n/cancel - Abort mission."
  
  RANGE_SELECTION_TXT = """<b>֎ Message Range ֎</b>

The range is set from message <code>{start}</code> to <code>{end}</code>.

You can confirm to start, or edit the range below."""

  UNEQUIFY_START_TXT = """<b>֎ Deduplicator ֎</b>

Select the target channel.

You can use /ubclist to find the Channel ID.

Manual input: `/unequify [channel_username_or_id]`"""
  
  CANCEL = "Process cancelled. (o˘◡˘o)"
  BOT_DETAILS = "<b>֎ Bot Details ֎</b>\n\n● <b>Name:</b> <code>{}</code>\n● <b>ID:</b> <code>{}</code>\n● <b>Username:</b> {}"
  USER_DETAILS = "<b>֎ Userbot Details ֎</b>\n\n● <b>Name:</b> <code>{}</code>\n● <b>ID:</b> <code>{}</code>\n● <b>Username:</b> {}"  
         
  TEXT = """<b>Forwarding Task: `{status}`</b>

`Fetched:    ` {fetched} / {total}
`Forwarded:  ` {forwarded}
`Skipped:    ` {skipped}
`Duplicates: ` {duplicates}

`Progress:   ` {progress_bar}
`Percentage: ` {percentage}%
`ETA:        ` {eta}
"""

  DUPLICATE_TEXT = """**Deduplication Task: `{status}`**"""

  STATUS_ALERT = """📊 **Real-Time Status** 📊

`Status:       ` {status}
`Processed:    ` {fetched} of {total}
`Forwarded:    ` {forwarded}
`Remaining:    ` {remaining}
`Skipped:      ` {skipped}
`Progress:     ` {percentage}%
`ETA:          ` {eta}
"""

  DOUBLE_CHECK = """<b>֎ Final Check ֎</b>

Here's the plan:

● <b>Using:</b> [{botname}](t.me/{botuname})
● <b>From:</b> <code>{from_chat}</code>
● <b>To:</b> <code>{to_chat}</code>
● <b>Range:</b> <code>{message_range}</code>

<i>Ensure [{botname}](t.me/{botuname}) is an admin in the target chat!</i>

<b>Proceed?</b>"""
  
  FORWARDELAY_TXT = """<b>֎ Forward Delay ֎</b>

Set a custom delay between forwards. Helps avoid API limits.

<b>Usage:</b> `/forwardelay [seconds]`
<b>Example:</b> `/forwardelay 0.5`

Default is 1 second."""
