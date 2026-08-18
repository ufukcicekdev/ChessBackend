"""Push a lightweight "something changed" event to a user's WebSocket group.

The client reacts by re-fetching the relevant data (challenges, etc.), so we
never have to replicate serialization here and there's no constant polling.
Safe no-op if the channel layer is unavailable.
"""
import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)


def notify_user(user_id, event=None):
    if not user_id:
        return
    layer = get_channel_layer()
    if layer is None:
        return
    try:
        async_to_sync(layer.group_send)(
            f"user_{user_id}",
            {"type": "notify", "event": event or {}},
        )
    except Exception:
        logger.warning("notify_user failed for user %s", user_id, exc_info=True)
