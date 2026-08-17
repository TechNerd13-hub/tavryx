import logging
from .config import settings
from .memory import MemoryStore
from .engine import TavryxEngine, command_response
from .models import IncomingMessage

log = logging.getLogger("tavryx.caspian")
memory = MemoryStore(settings.db_path)


def start_caspian_listener():
    try:
        from caspian_sdk import CommClient
    except ImportError:
        log.exception("caspian-sdk is not installed")
        return
    if not settings.caspian_api_key:
        log.error("CASPIAN_API_KEY is not configured")
        return
    try:
        engine = TavryxEngine(memory)
        client = CommClient()

        @client.on_message
        def handle(message):
            text = (message.text or "").strip()
            if not text:
                return
            sender = (message.sender or {}).get("address", "unknown")
            channel = getattr(message, "channel", None) or "caspian"
            parts = text.split()
            command = parts[0].lower() if parts and parts[0].startswith("/") else None
            argument = parts[1] if len(parts) > 1 else None
            try:
                result = command_response(command, memory, argument) if command else None
                if result is None:
                    result = engine.analyze(IncomingMessage(
                        text=text, sender=sender, channel=channel,
                        message_id=getattr(message, "id", None)
                    )).response
                message.reply(result)
            except Exception:
                log.exception("Failed to process message")
                try:
                    # Never expose internals or claim that state was changed.
                    message.reply(
                        "**TAVRYX · RECOVERING**\n\n"
                        "I couldn't safely update this situation right now. "
                        "Your last known state is preserved. Please retry and I'll continue from there."
                    )
                except Exception:
                    log.exception("Failed to send recovery response")
        log.info("TAVRYX listener active — one handler across connected channels")
        client.listen()
    except Exception:
        log.exception("Caspian listener stopped unexpectedly")
