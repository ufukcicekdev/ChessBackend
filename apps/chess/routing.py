from django.urls import re_path
from .consumers import ChessConsumer

websocket_urlpatterns = [
    re_path(r"ws/chess/(?P<room_id>[0-9a-f-]+)/$", ChessConsumer.as_asgi()),
]
