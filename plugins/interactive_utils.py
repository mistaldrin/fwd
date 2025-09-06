# Dawn Interactive Utilities
# This file contains the shared logic for interactive command flows.
# Created to keep original plugin files clean and modularize new features.

import asyncio
from telethon import Button, events
from telethon.tl.types import Channel
from telethon.tl.functions.messages import GetMessagesViewsRequest

# Imports from your project's core structure
from fwd import BOTLOG_CHATID, DAWN_USERS, bot
from fwd.userbot import USERBOT_ID_S, USERBOTS

# --- SHARED STATE & HELPER FUNCTIONS ---

CONVO_STATE = {}  # Manages all interactive conversations state by user_id

async def get_chats_for_client(client_id):
    """(Helper) Fetches a list of chats for a given userbot client."""
    client = USERBOTS.get(f"userbot_{client_id}")
    if not client or not client.is_connected():
        return None
    chats = []
    try:
        dialogs = await client.get_dialogs(limit=None)
    except Exception as e:
        print(f"[InteractiveUtils] Could not get dialogs for userbot_{client_id}: {e}")
        return []

    for dialog in dialogs:
        can_send = True
        # Logic to check send permissions
        if hasattr(dialog.entity, "banned_rights") and dialog.entity.banned_rights.send_messages:
            can_send = False
        if isinstance(dialog.entity, Channel) and not dialog.entity.megagroup:
            if not dialog.entity.creator and (not dialog.entity.admin_rights or not dialog.entity.admin_rights.post_messages):
                can_send = False
        chats.append({'name': dialog.name or "Deleted Account", 'id': dialog.id, 'can_send': can_send})
    return chats

async def get_range_selection_text_and_buttons(user_id):
    """(Helper) Generates the UI for the message range selection step."""
    state = CONVO_STATE.get(user_id, {})
    command = state.get("command", "operation")
    start_id = state.get("start_id", "Not Set")
    end_id = state.get("end_id", "Not Set")
    order_text = "Oldest ➜ Newest" if state.get("oldest_first", True) else "Newest ➜ Oldest"

    text = f"**{command.capitalize()} Setup**\n\nPlease define the message range for the operation."
    buttons = [
        [Button.inline(f"Start ID: {start_id}", data="set_start"), Button.inline(f"End ID: {end_id}", data="set_end")],
        [Button.inline(f"Order: {order_text}", data="toggle_order")],
        [Button.inline(f"✅ Confirm & Proceed", data="confirm_op")],
        [Button.inline("❌ Cancel", data="cancel_convo")]
    ]
    return text, buttons

# --- INTERACTIVE FLOW STARTERS ---

async def start_interactive_flow(event, command):
    """(Trigger) Initiates the interactive process for /fwd or /unequify."""
    user_id = event.sender_id
    if user_id in CONVO_STATE:
        return await event.reply("`You already have an active operation. Please cancel it first.`")

    state = {
        "command": command,
        "step": "select_userbot",
        "original_chat_id": event.chat_id,
    }
    CONVO_STATE[user_id] = state

    buttons, row = [], []
    for uid in USERBOT_ID_S:
        client = USERBOTS.get(f"userbot_{uid}")
        if client and client.is_connected():
            me = await client.get_me(); row.append(Button.inline(me.first_name, data=f"select_ub_{uid}"))
            if len(row) == 2:
                buttons.append(row); row = []
    if row: buttons.append(row)

    if not buttons:
        CONVO_STATE.pop(user_id, None); return await event.reply("`No connected userbots found.`")

    buttons.append([Button.inline("❌ Cancel", data="cancel_convo")])
    prompt = ("`Select the userbot to forward FROM (determines source chat list):`" if command == "forward"
              else "`Please select the userbot that is in the target chat:`")
    msg = await event.reply(prompt, buttons=buttons)
    state["last_msg_id"] = msg.id

# --- CALLBACK & REPLY HANDLERS ---

@bot.on(events.CallbackQuery(pattern=b"select_ub_"))
async def cb_userbot_select(event):
    user_id = event.sender_id
    state = CONVO_STATE.get(user_id)
    if not state or state["step"] != "select_userbot": return await event.answer()

    await event.edit("`Fetching chats, please wait...`")
    userbot_id = int(event.data.decode().split("_")[-1])
    state["userbot_id"] = userbot_id
    chats = await get_chats_for_client(userbot_id)
    if not chats:
        CONVO_STATE.pop(user_id, None); return await event.edit("`This userbot is not in any chats or failed to fetch them.`")

    state["chats"], state["step"] = chats, "select_chat"
    prompt = "**Reply to this message with the S.N. or Chat ID to select the chat:**\n\n"
    message_lines = [prompt] + [f"**{i}**. {c['name']} (`{c['id']}`)" for i, c in enumerate(chats, 1)]

    full_text = ""
    for line in message_lines:
        if len(full_text) + len(line) > 4000:
            await event.client.send_message(event.chat_id, full_text, reply_to=state["last_msg_id"]); full_text = ""
        full_text += line + "\n"
    await event.edit(full_text, buttons=[Button.inline("❌ Cancel", data="cancel_convo")])

@bot.on(events.NewMessage(from_users=DAWN_USERS, func=lambda e: e.is_reply))
async def handle_interactive_replies(event):
    user_id = event.sender_id
    state = CONVO_STATE.get(user_id)
    if not state or not event.reply_to or event.reply_to.reply_to_msg_id != state.get("last_msg_id"): return

    step = state.get("step")
    await event.delete()

    if step == "select_chat":
        chats, selected_chat = state.get("chats", []), None
        try:
            val = event.text.strip()
            # Handle both serial number and direct chat ID
            if val.lstrip('-').isdigit():
                val = int(val)
                if 1 <= val <= len(chats):
                    selected_chat = chats[val - 1]
                else:
                    selected_chat = next((c for c in chats if c["id"] == val), None)
        except (ValueError, TypeError):
             return # Ignore non-numeric input

        if not selected_chat: return
        state["target_chat_id"], state["step"] = selected_chat["id"], "range_selection"
        text, buttons = await get_range_selection_text_and_buttons(user_id)
        await bot.edit_message(user_id, state["last_msg_id"], text, buttons=buttons)

    elif step == "range_selection" and "awaiting_input" in state:
        input_type = state.pop("awaiting_input")
        try:
            state[input_type] = int(event.text)
            text, buttons = await get_range_selection_text_and_buttons(user_id)
            await bot.edit_message(user_id, state["last_msg_id"], text, buttons=buttons)
        except (ValueError, TypeError): pass

@bot.on(events.CallbackQuery(pattern=b"set_(start|end)"))
async def cb_set_range(event):
    user_id, state = event.sender_id, CONVO_STATE.get(event.sender_id)
    if not state or state.get('step') != 'range_selection': return await event.answer()
    action = event.data.decode().split('_')[1]
    state['awaiting_input'] = f"{action}_id"
    await event.edit(f"`Please reply to this message with the {action.capitalize()} Message ID.`", buttons=[Button.inline("❌ Cancel", data="cancel_convo")])

@bot.on(events.CallbackQuery(pattern=b"toggle_order"))
async def cb_toggle_order(event):
    user_id, state = event.sender_id, CONVO_STATE.get(event.sender_id)
    if not state or state.get('step') != 'range_selection': return await event.answer()
    state['oldest_first'] = not state.get('oldest_first', True)
    text, buttons = await get_range_selection_text_and_buttons(user_id)
    await event.edit(text, buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"cancel_convo"))
async def cb_cancel_convo(event):
    if event.sender_id in CONVO_STATE:
        CONVO_STATE.pop(event.sender_id, None); await event.edit("`Operation cancelled.`")
    else: await event.answer()

@bot.on(events.CallbackQuery(pattern=b"confirm_op"))
async def cb_confirm_op(event):
    user_id, state = event.sender_id, CONVO_STATE.get(event.sender_id)
    if not state or state.get("step") != "range_selection": return await event.answer()
    if not state.get("start_id") or not state.get("end_id"): return await event.answer("Start and End IDs must be set.", alert=True)

    await event.edit("`Processing your request...`")
    command = state['command']
    if command == "unequify": await execute_unequify_interactive(state)
    elif command == "forward": await execute_forward_interactive(state)
    CONVO_STATE.pop(user_id, None)

# --- EXECUTION LOGIC ---

async def execute_unequify_interactive(state):
    chat_id, ubot_id = state["target_chat_id"], state["userbot_id"]
    msg_ids = list(range(state["start_id"], state["end_id"] + 1))
    if not state.get("oldest_first", True): msg_ids.reverse()
    ubot = USERBOTS[f"userbot_{ubot_id}"]
    await bot.send_message(state["original_chat_id"], f"`Starting to unequify {len(msg_ids)} messages in {chat_id}...`")
    s, f = 0, 0
    for i in msg_ids:
        try:
            await ubot(GetMessagesViewsRequest(peer=chat_id, id=[i], increment=True)); s += 1; await asyncio.sleep(1.5)
        except Exception as e:
            f += 1; await bot.send_message(BOTLOG_CHATID, f"**Unequify Error in `{chat_id}` msg `{i}`:**\n`{e}`")
    await bot.send_message(state["original_chat_id"], f"**Unequify Complete!**\n- Success: `{s}`\n- Failed: `{f}`")

async def execute_forward_interactive(state):
    from_chat, to_chat = state["target_chat_id"], state["original_chat_id"]
    msg_ids = list(range(state["start_id"], state["end_id"] + 1))
    if not state.get("oldest_first", True): msg_ids.reverse()
    ubot = USERBOTS[f"userbot_{state['userbot_id']}"]
    await bot.send_message(to_chat, f"`Forwarding {len(msg_ids)} messages from {from_chat} to {to_chat}...`")
    s, f = 0, 0
    for mid in msg_ids:
        try:
            await ubot.forward_messages(to_chat, mid, from_chat); s += 1; await asyncio.sleep(2)
        except Exception as e:
            f += 1; await bot.send_message(BOTLOG_CHATID, f"**Forward Error from `{from_chat}` msg `{mid}`:**\n`{e}`")
    await bot.send_message(to_chat, f"**Forwarding Complete!**\n- Success: `{s}`\n- Failed: `{f}`")
