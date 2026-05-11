import asyncio
import httpx
import logging
import os
from collections import defaultdict

TELEGRAM_API = "https://api.telegram.org"
MAX_LEN = 4096
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

SEVERITY_ICON = {"critical": "🔴", "warning": "🟡", "info": "🔵"}
logger = logging.getLogger(__name__)

_TYPING_INTERVAL = 4
_MAX_HISTORY_TURNS = 10

# Per-chat conversation history: {chat_id: [{"user": ..., "assistant": ...}, ...]}
_history: dict[str, list[dict]] = defaultdict(list)


def _build_prompt(chat_id: str, query: str) -> str:
    turns = _history[chat_id][-_MAX_HISTORY_TURNS:]
    if not turns:
        return query
    lines = ["[Conversation history]"]
    for t in turns:
        lines.append(f"User: {t['user']}")
        lines.append(f"Assistant: {t['assistant']}")
    lines += ["", "[New message]", query]
    return "\n".join(lines)


def _save_turn(chat_id: str, query: str, response: str) -> None:
    _history[chat_id].append({"user": query, "assistant": response})
    if len(_history[chat_id]) > _MAX_HISTORY_TURNS:
        _history[chat_id] = _history[chat_id][-_MAX_HISTORY_TURNS:]


def clear_history(chat_id: str) -> None:
    _history[chat_id].clear()


async def send(text: str, chat_id: str = "", reply_to_message_id: int | None = None) -> int | None:
    """Send a message and return the message_id of the first chunk."""
    target = chat_id or CHAT_ID
    if not BOT_TOKEN or not target:
        logger.info("[telegram disabled] output:\n%s", text)
        return None

    chunks = [text[i:i + MAX_LEN] for i in range(0, len(text), MAX_LEN)]
    first_message_id = None
    async with httpx.AsyncClient(timeout=10) as client:
        for i, chunk in enumerate(chunks):
            body: dict = {"chat_id": target, "text": chunk, "parse_mode": "Markdown"}
            if reply_to_message_id and i == 0:
                body["reply_to_message_id"] = reply_to_message_id
            resp = await client.post(f"{TELEGRAM_API}/bot{BOT_TOKEN}/sendMessage", json=body)
            data = resp.json()
            if not data.get("ok"):
                logger.warning("[telegram] sendMessage failed (Markdown): %s — retrying as plain text", resp.text)
                body.pop("parse_mode", None)
                resp = await client.post(f"{TELEGRAM_API}/bot{BOT_TOKEN}/sendMessage", json=body)
                data = resp.json()
                if not data.get("ok"):
                    logger.error("[telegram] sendMessage failed: %s", resp.text)
            if first_message_id is None:
                first_message_id = data.get("result", {}).get("message_id")
    return first_message_id


async def send_alert_notification(alert_name: str, severity: str, summary: str, chat_id: str = "") -> int | None:
    """Send the initial alert notification and return its message_id."""
    icon = SEVERITY_ICON.get(severity.lower(), "⚪")
    text = f"{icon} *{alert_name}*\n_{summary}_\n\n🔍 Investigating..."
    return await send(text, chat_id)


async def send_analysis(alert_name: str, severity: str, analysis: str, reply_to_message_id: int | None = None) -> None:
    icon = SEVERITY_ICON.get(severity.lower(), "⚪")
    await send(f"{icon} *{alert_name}* — Analysis\n\n{analysis}", reply_to_message_id=reply_to_message_id)


async def _send_typing(chat_id: str, stop_event: asyncio.Event) -> None:
    """Keep sending 'typing...' action until stop_event is set."""
    async with httpx.AsyncClient(timeout=5) as client:
        while not stop_event.is_set():
            await client.post(
                f"{TELEGRAM_API}/bot{BOT_TOKEN}/sendChatAction",
                json={"chat_id": chat_id, "action": "typing"},
            )
            await asyncio.sleep(_TYPING_INTERVAL)


async def _get_updates(offset: int) -> list[dict]:
    async with httpx.AsyncClient(timeout=35) as client:
        resp = await client.get(
            f"{TELEGRAM_API}/bot{BOT_TOKEN}/getUpdates",
            params={"offset": offset, "timeout": 30, "allowed_updates": ["message"]},
        )
        resp.raise_for_status()
        return resp.json().get("result", [])


async def start_polling(run_claude_fn) -> None:
    """
    Long-poll Telegram for messages. Calls run_claude_fn(prompt) for each
    user message and replies in the same chat.

    Trigger keywords: any message (in private chat) or messages starting with
    /ask or mentioning the bot username.
    """
    if not BOT_TOKEN:
        logger.info("[telegram polling] BOT_TOKEN not set — polling disabled")
        return

    # Get bot username for @mention detection
    bot_username = ""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            me = (await client.get(f"{TELEGRAM_API}/bot{BOT_TOKEN}/getMe")).json()
            bot_username = "@" + me.get("result", {}).get("username", "")
            logger.info(f"[telegram polling] Started as {bot_username}")
    except Exception as e:
        logger.warning(f"[telegram polling] Could not fetch bot info: {e}")

    offset = 0
    while True:
        try:
            updates = await _get_updates(offset)
        except Exception as e:
            logger.warning(f"[telegram polling] getUpdates error: {e}")
            await asyncio.sleep(5)
            continue

        for update in updates:
            offset = update["update_id"] + 1
            message = update.get("message", {})
            text = message.get("text", "").strip()
            chat_id = str(message.get("chat", {}).get("id", ""))
            chat_type = message.get("chat", {}).get("type", "")

            if not text or not chat_id:
                continue

            # Accept: private chats (any message), or /ask command, or @mention
            is_private = chat_type == "private"
            is_command = text.startswith("/ask ")
            is_mention = bot_username and bot_username.lower() in text.lower()

            if not (is_private or is_command or is_mention):
                continue

            # Strip trigger prefix to get the actual query
            query = text
            if is_command:
                query = text[5:].strip()
            elif is_mention:
                query = text.replace(bot_username, "").strip()

            # /reset clears conversation memory for this chat
            if text.strip() in ("/reset", "/reset@" + bot_username.lstrip("@")):
                clear_history(chat_id)
                await send("Conversation history cleared.", chat_id)
                continue

            if not query:
                await send("Send me a question or command, e.g.:\n`/ask check IAM users`", chat_id)
                continue

            logger.info(f"[telegram] Received query from {chat_id}: {query[:80]}")

            asyncio.create_task(_handle_query(query, chat_id, run_claude_fn))


async def _handle_query(query: str, chat_id: str, run_claude_fn) -> None:
    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(_send_typing(chat_id, stop_typing))

    try:
        prompt = _build_prompt(chat_id, query)
        analysis = await run_claude_fn(prompt)
        stop_typing.set()
        await typing_task
        _save_turn(chat_id, query, analysis)
        await send(analysis, chat_id)
    except Exception as e:
        stop_typing.set()
        await typing_task
        logger.exception(f"[telegram] Query handling failed: {e}")
        await send(f"Analysis failed: {e}", chat_id)
