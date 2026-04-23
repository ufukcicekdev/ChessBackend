from channels.middleware import BaseMiddleware
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth import get_user_model

User = get_user_model()


def _parse_qs(query_string: str) -> dict:
    params = {}
    for part in query_string.split("&"):
        if "=" in part:
            k, v = part.split("=", 1)
            params[k] = v
    return params


@database_sync_to_async
def get_user_from_ticket(ticket: str):
    try:
        import redis as redis_lib
        from django.conf import settings
        r = redis_lib.from_url(settings.REDIS_URL or "", decode_responses=True)
        key = f"ws_ticket:{ticket}"
        user_id = r.get(key)
        if not user_id:
            return AnonymousUser()
        r.delete(key)  # one-time use
        return User.objects.get(id=int(user_id))
    except Exception:
        return AnonymousUser()


@database_sync_to_async
def get_user_from_token(token_str: str):
    try:
        token = AccessToken(token_str)
        return User.objects.get(id=token["user_id"])
    except Exception:
        return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        query_string = scope.get("query_string", b"").decode()
        params = _parse_qs(query_string)

        if "ticket" in params:
            scope["user"] = await get_user_from_ticket(params["ticket"])
        elif "token" in params:
            scope["user"] = await get_user_from_token(params["token"])
        else:
            scope["user"] = AnonymousUser()

        return await super().__call__(scope, receive, send)


def JWTAuthMiddlewareStack(inner):
    return JWTAuthMiddleware(inner)
