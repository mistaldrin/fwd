import os
from config import Config

class Translation(object):
  START_TXT = """wassup {}

<i>Personal Past Forwarding Bot</i>

<b>Click '⊛ Hᴇʟᴩ ⊛' for... Help duh...</b>"""


  HELP_TXT = """<b><u>⋈ Hᴇʟᴩ</b></u>

<b><u>≍ Aᴠᴀɪʟᴀʙʟᴇ Cᴏᴍᴍᴀɴᴅꜱ :</u></b>
⏣ __/start - Cʜᴇᴄᴋ I'ᴍ Aʟɪᴠᴇ__ 
⏣ __/forward - Fᴏʀᴡᴀʀᴅ Mᴇꜱꜱᴀɢᴇꜱ Iɴ A Rᴀɴɢᴇ__
⏣ __/unequify - Dᴇʟᴇᴛᴇ Dᴜᴩʟɪᴄᴀᴛᴇ Mᴇꜱꜱᴀɢᴇꜱ Iɴ A Rᴀɴɢᴇ__
⏣ __/ubclist - Lɪꜱᴛ Cʜᴀᴛꜱ Fʀᴏᴍ Yᴏᴜʀ Usᴇʀʙᴏᴛ__
⏣ __/settings - Cᴏɴꜰɪɢᴜʀᴇ Yᴏᴜʀ Sᴇᴛᴛɪɴɢꜱ__
⏣ __/reset - Rᴇꜱᴇᴛ Yᴏᴜʀ Sᴇᴛᴛɪɴɢꜱ__
⏣ __/forwardelay - Sᴇᴛ ᴀ ᴄᴜꜱᴛᴏᴍ ꜰᴏʀᴡᴀʀᴅɪɴɢ ᴅᴇʟᴀʏ__

<b><u>≬≬ Fᴇᴀᴛᴜʀᴇꜱ :</b></u>
► __Sᴇʟᴇᴄᴛ A Sᴘᴇᴄɪғɪᴄ Rᴀɴɢᴇ Oꜰ Mᴇssᴀɢᴇs Tᴏ Fᴏʀᴡᴀʀᴅ Oʀ Dᴇᴅᴜᴘʟɪᴄᴀᴛᴇ__
► __Iɴᴛᴇʀᴀᴄᴛɪᴠᴇʟʏ Sᴇʟᴇᴄᴛ Cʜᴀᴛs Fᴏʀ Dᴇᴅᴜᴘʟɪᴄᴀᴛɪᴏɴ__
► __Fᴏʀᴡᴀʀᴅ Mᴇꜱꜱᴀɢᴇ Fʀᴏᴍ Pᴜʙʟɪᴄ Cʜᴀɴɴᴇʟ To Yᴏᴜʀ Cʜᴀɴɴᴇʟ Wɪᴛʜᴏᴜᴛ Aᴅᴍɪɴ Peᴇʀᴍɪꜱꜱɪᴏɴ__
► __Forward Message Fʀᴏᴍ Private Cʜᴀɴɴᴇʟ To Yᴏᴜʀ Cʜᴀɴɴᴇʟ Bʏ Uꜱɪɴɢ UꜱᴇʀBᴏᴛ__
► __Cᴜꜱᴛᴏм Cᴀᴩᴛɪᴏɴ & Bᴜᴛᴛᴏɴ__
► __Sᴜᴩᴩᴏʀᴛ Rᴇꜱᴛʀɪᴄᴛᴇḍ Cʜᴀᴛꜱ__
► __Sᴋɪᴩ Dᴜᴩʟɪᴄᴀᴛᴇ Mᴇꜱꜱᴀɢᴇꜱ__
"""
  
  HOW_USE_TXT = """<b><u>⚠️ Bᴇꜰᴏʀᴇ Fᴏʀᴡᴀʀᴅ :</b></u>
  
► __Aᴅᴅ A Bᴏᴛ Oʀ Uꜱᴇʀʙᴏᴛ__
► __Aᴅᴅ Aᴛʟᴇᴀꜱᴛ Oɴᴇ Cʜᴀᴛ Tᴏ Cʜᴀɴɴᴇʟꜱ (Yᴏᴜʀ Bᴏᴛ/UꜱᴇʀBᴏᴛ Mᴜꜱᴛ Bᴇ Aᴅᴍɪɴ Tʜᴇʀᴇ)__
► __Yᴏᴜ Cᴀɴ Aᴅᴅ Cʜᴀᴛꜱ Oʀ Bᴏᴛꜱ Bʏ Uꜱɪɴɢ /settings__
► __Iꜰ Tʜᴇ **Fʀᴏᴍ Cʜᴀɴɴᴇʟ** Iꜱ Pʀɪᴠᴀᴛᴇ, Yᴏᴜʀ UꜱᴇʀBᴏᴛ Mᴜꜱᴛ Bᴇ A Mᴇᴍʙᴇʀ Iɴ Tʜᴇʀᴇ Oʀ Yᴏᴜʀ Bᴏᴛ Mᴜꜱᴛ Nᴇᴇᴅ Tᴏ Bᴇ Aᴅᴍɪɴ Iɴ Tʜᴇʀᴇ Aʟꜱᴏ__
► __Tʜᴇɴ Uꜱᴇ /forward Tᴏ Fᴏʀᴡᴀʀᴅ Mᴇꜱꜱᴀɢᴇꜱ, Wʜᴇʀᴇ Iᴛ Aꜱᴋ Fᴏʀ Sᴏᴜʀᴄᴇ Cʜᴀᴛ Tᴏ Fᴏᴡᴀʀᴅ__"""
  
  ABOUT_TXT = """<b>⋉ Mʏ Nᴀᴍᴇ :</b> {}
<b>⋉ Lᴀɴɢᴜᴀɢᴇ :</b> <a>English</a>
<b>⋉ Lɪʙʀᴀʀʏ :</b> <a>Pyrogram</a>
<b>⋉ Sᴇʀᴠᴇʀ :</b> <a>Koyeb</a>
<b>⋉ Cʜᴀɴɴᴇʟ :</b> <a href='https://t.me/norFederation'>norFed</a>
<b>⋉ Dᴇᴠᴇʟᴏᴩᴇʀ :</b> <a href='https://t.me/partDevil'>partDevil</a>"""
  
  STATUS_TXT = """<b><u>Bᴏᴛ Sᴛᴀᴛᴜꜱ:</u></b>
  
<b>⊛ Tᴏᴛᴀʟ Uꜱᴇʀꜱ :</b> <code>{}</code>
<b>⚝ Tᴏᴛᴀʟ Bᴏᴛꜱ :</b> <code>{}</code>
<b>❉ Fᴏʀᴡᴀʀᴅɪɴɢ :</b> <code>{}</code>
"""
  
  FROM_MSG = "<b><u>Sᴇᴛ Sᴏᴜʀᴄᴇ Cʜᴀᴛ</></>\n\nForward The Last Mᴇꜱꜱᴀɢᴇ Or Last Mᴇꜱꜱᴀɢᴇ Lɪɴᴋ Oꜰ Sᴏᴜʀᴄᴇ Cʜᴀᴛ.\n/cancel - Tᴏ Cᴀɴᴄᴇʟ Tʜɪꜱ Pʀᴏᴄᴇꜱꜱ"
  TO_MSG = "<b><u>Cʜᴏᴏꜱᴇ Tᴀʀɢᴇᴛ Cʜᴀᴛ</u></b>\n\nCʜᴏᴏꜱᴇ Yᴏᴜʀ Tᴀʀɢᴇᴛ Cʜᴀᴛ Fʀᴏᴍ Tʜᴇ Gɪᴠᴇɴ Bᴜᴛᴛᴏɴꜱ.\n/cancel - Tᴏ Cᴀɴᴄᴇʟ Tʜɪꜱ Pʀᴏᴄᴇꜱꜱ"
  
  RANGE_SELECTION_TXT = """<b><u>SELECT MESSAGE RANGE</u></b>

You can either forward all messages by default or specify a custom range using the buttons below.

<i>Note: Forwarding all messages from a very large channel may take a significant amount of time.</i>"""

  UNEQUIFY_START_TXT = """<b><u>Advanced Deduplicator</u></b>

How would you like to select the target channel?

**Usage:** `/unequify [channel_username or chat_id]` for manual input."""
  
  CANCEL = "<b> Pʀᴏᴄᴇꜱꜱ Cᴀɴᴄᴇʟʟᴇᴅ Sᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ! </b>"
  BOT_DETAILS = "<b><u>📄 Bᴏᴛ Dᴇᴛᴀɪʟꜱ</u></b>\n\n<b>➣ Nᴀᴍᴇ :</b> <code>{}</code>\n<b>➣ Bᴏᴛ ID :</b> <code>{}</code>\n<b>➣ Uꜱᴇʀɴᴀᴍᴇ :</b> @{}"
  USER_DETAILS = "<b><u>📄 UꜱᴇʀBᴏᴛ Dᴇᴛᴀɪʟꜱ</u></b>\n\n<b>➣ Nᴀᴍᴇ :</b> <code>{}</code>\n<b>➣ Uꜱᴇʀ ID :</b> <code>{}</code>\n<b>➣ Uꜱᴇʀɴᴀᴍᴇ :</b> @{}"  
         
  TEXT = """<b><u>Fᴏʀᴡᴀʀᴅ Sᴛᴀᴛᴜꜱ</u></b>
  
<b>🎯 Total In Range:</b> <code>{total}</code>
<b>🕵 Fᴇᴛᴄʜᴇᴅ Mᴇꜱꜱᴀɢᴇ :</b> <code>{}</code>
<b>✅ Sᴜᴄᴄᴇꜱꜰᴜʟʟʏ Fᴏʀᴡᴀʀᴅ :</b> <code>{}</code>
<b>👥 Dᴜʙʟɪᴄᴀᴛᴇ Mᴇꜱꜱᴀɢᴇ :</b> <code>{}</code>
<b>🗑 Dᴇʟᴇᴛᴇᴅ Mᴇꜱꜱᴀɢᴇ :</b> <code>{}</code>
<b>🔁 Fɪʟᴛᴇʀᴇᴅ Mᴇꜱꜱᴀɢᴇ :</b> <code>{}</code>
<b>📊 Cᴜʀʀᴇɴᴛ Sᴛᴀᴛᴜꜱ :</b> <code>{}</code>
<b>🔥 Pᴇʀᴄᴇɴᴛᴀɢᴇ :</b> <code>{}</code> %

{}
"""

  DUPLICATE_TEXT = """<b><u>UɴᴇQᴜɪꜰʏ Sᴛᴀᴛᴜꜱ</u></b>

<b>🎯 Total In Range:</b> <code>{total}</code>
<b>🕵 Mᴇssᴀɢᴇs Sᴄᴀɴɴᴇᴅ :</b> <code>{}</code>
<b>👥 Dᴜʙʟɪᴄᴀᴛᴇ Dᴇʟᴇᴛᴇᴅ :</b> <code>{}</code>

{}
"""
  DOUBLE_CHECK = """<b><u>Dᴏᴜʙʟᴇ Cʜᴇᴄᴋɪɴɢ</u></b>
  
Bᴇꜰᴏʀ Fᴏʀᴡᴀʀᴅɪɴɢ Tʜᴇ Mᴇꜱꜱᴀɢᴇꜱ Cʟɪᴄᴋ Tʜᴇ Yᴇꜱ Bᴜᴛᴛᴏɴ Oɴʟʏ Aꜰᴛᴇʀ Cʜᴇᴄᴋɪɴɢ Tʜᴇ Fᴏʟʟᴏᴡɪɴɢ

<b>★ Yᴏᴜʀ Bᴏᴛ :</b> [{botname}](t.me/{botuname})
<b>★ Fʀᴏᴍ Cʜᴀɴɴᴇʟ :</b> <code>{from_chat}</code>
<b>★ Tᴏ Cʜᴀɴɴᴇʟ :</b> <code>{to_chat}</code>
<b>★ Mᴇssᴀɢᴇ Rᴀɴɢᴇ :</b> <code>{message_range}</code>

<i>° [{botname}](t.me/{botuname}) Mᴜꜱᴛ Bᴇ Aᴅᴍɪɴ Iɴ <b>Tᴀʀɢᴇᴛ Cʜᴀᴛ</b></i> (<code>{to_chat}</code>)
<i>° Iꜰ Tʜᴇ <b>Sᴏᴜʀᴄᴇ Cʜᴀᴛ</b> Iꜱ Pʀɪᴠᴀᴛᴇ Yᴏᴜʀ Userbot Mᴜꜱᴛ Bᴇ Mᴇᴍʙᴇʀ Or Yᴏᴜʀ Bᴏᴛ Mᴜꜱᴛ Bᴇ Aᴅᴍɪɴ Iɴ Tʜᴇʀᴇ Aʟꜱᴏ</i>

<b>Iꜰ Tʜᴇ Aʙᴏᴠᴇ Iꜱ Cʜᴇᴄᴋᴇᴅ Tʜᴇɴ Tʜᴇ Yᴇꜱ Bᴜᴛᴛᴏɴ Cᴀɴ Bᴇ Cʟɪᴄᴋᴇᴅ</b>"""
  
  FORWARDELAY_TXT = """<b><u>Set Forwarding Delay</u></b>

Use this command to set a custom delay (in seconds) between forwarded messages to avoid Telegram's flood limits.

<b>Usage:</b> <code>/forwardelay [delay_in_seconds]</code>
<b>Example:</b> <code>/forwardelay 0.5</code> (sets a half-second delay)
<b>Example:</b> <code>/forwardelay 2</code> (sets a two-second delay)

The default delay is 1 second."""
