"""Firebase Cloud Messaging helper.

Safe to import and call even when Firebase is not configured — in that case
every send is a no-op (so local dev / CI never breaks). Configure by setting
FIREBASE_CREDENTIALS to the path of a service-account JSON file.
"""
import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

_app = None
_init_failed = False


def _get_app():
    """Lazily initialise (and cache) the firebase-admin app, or return None."""
    global _app, _init_failed
    if _app is not None:
        return _app
    if _init_failed:
        return None

    cred_source = getattr(settings, "FIREBASE_CREDENTIALS", None)
    if not cred_source:
        _init_failed = True
        return None

    try:
        import firebase_admin
        from firebase_admin import credentials

        # Accept either a file path or the raw JSON string (handy for env vars).
        if cred_source.strip().startswith("{"):
            cred = credentials.Certificate(json.loads(cred_source))
        else:
            cred = credentials.Certificate(cred_source)

        _app = firebase_admin.initialize_app(cred)
        return _app
    except Exception as e:  # pragma: no cover - depends on external creds
        logger.warning("FCM init failed, notifications disabled: %s", e)
        _init_failed = True
        return None


def send_to_users(user_ids, title, body, data=None, link="/"):
    """Send a push notification to every registered device of the given users.

    No-op if Firebase isn't configured or the users have no devices.
    Invalid/expired tokens are pruned automatically.
    """
    app = _get_app()
    if not app or not user_ids:
        return

    from firebase_admin import messaging
    from .models import FCMDevice

    tokens = list(
        FCMDevice.objects.filter(user_id__in=user_ids).values_list("token", flat=True)
    )
    if not tokens:
        return

    payload = {k: str(v) for k, v in (data or {}).items()}
    payload["link"] = link  # our service worker navigates using this on click

    # WebpushFCMOptions.link must be an absolute HTTPS URL; only set it then.
    # (Our SW's notificationclick handler uses data.link regardless, so this is
    # just for FCM's default click behaviour on https origins.)
    webpush = None
    if link.startswith("https://"):
        webpush = messaging.WebpushConfig(
            fcm_options=messaging.WebpushFCMOptions(link=link),
        )

    message = messaging.MulticastMessage(
        tokens=tokens,
        notification=messaging.Notification(title=title, body=body),
        data=payload,
        webpush=webpush,
    )

    try:
        resp = messaging.send_each_for_multicast(message)
    except Exception as e:  # pragma: no cover
        logger.warning("FCM send failed: %s", e)
        return

    # Prune tokens that the FCM backend reported as invalid/unregistered.
    invalid = []
    for token, result in zip(tokens, resp.responses):
        if not result.success and result.exception is not None:
            code = getattr(result.exception, "code", "") or ""
            if any(x in str(code).lower() for x in ("not-registered", "invalid-argument", "unregistered")):
                invalid.append(token)
    if invalid:
        FCMDevice.objects.filter(token__in=invalid).delete()
