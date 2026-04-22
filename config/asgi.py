import os

# Must be set before importing anything that touches Django settings.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter

django_asgi_app = get_asgi_application()

# Delay importing app code until Django is initialized.
from apps.chess.middleware import JWTAuthMiddlewareStack
import apps.chess.routing as chess_routing

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": JWTAuthMiddlewareStack(
            URLRouter(chess_routing.websocket_urlpatterns)
        ),
    }
)
