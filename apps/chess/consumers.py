import json
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from .models import Game, Move, Room


class ChessConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for a chess room.

    URL: ws://.../ws/chess/<room_id>/?token=<jwt>

    Message types sent by client:
      - join:       Player joins the room and picks a color.
      - move:       Player submits a move.
      - resign:     Player resigns.
      - draw_offer: Player offers a draw.
      - draw_accept / draw_decline

    Broadcasts to group (players + spectators):
      - game_state: Full board state after a move.
      - player_joined / player_left
      - game_over
      - draw_offer / draw_result
      - error (only to sender)
    """

    async def connect(self):
        self.room_id = self.scope["url_route"]["kwargs"]["room_id"]
        self.room_group = f"chess_{self.room_id}"
        self.user = self.scope["user"]
        self.role = "spectator"  # upgraded to "white" or "black" on join

        await self.channel_layer.group_add(self.room_group, self.channel_name)
        await self.accept()

        # Send current game state immediately so spectators/rejoining players sync up
        state = await self.get_game_state()
        if state:
            await self.send(text_data=json.dumps({"type": "game_state", **state}))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group, self.channel_name)
        if self.role in ("white", "black"):
            await self.channel_layer.group_send(
                self.room_group,
                {"type": "player_left_event", "player": self.role, "username": self.username},
            )

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send_error("Invalid JSON")
            return

        msg_type = data.get("type")
        handlers = {
            "join": self.handle_join,
            "move": self.handle_move,
            "resign": self.handle_resign,
            "draw_offer": self.handle_draw_offer,
            "draw_accept": self.handle_draw_accept,
            "draw_decline": self.handle_draw_decline,
        }
        handler = handlers.get(msg_type)
        if handler:
            await handler(data)
        else:
            await self.send_error(f"Unknown message type: {msg_type}")

    # ------------------------------------------------------------------ #
    #  Handlers                                                            #
    # ------------------------------------------------------------------ #

    async def handle_join(self, data):
        if self.user.is_anonymous:
            await self.send_error("Authentication required to join as a player")
            return

        result = await self.assign_player_color()
        if result["error"]:
            await self.send_error(result["error"])
            return

        self.role = result["color"]
        self.username = self.user.username

        await self.channel_layer.group_send(
            self.room_group,
            {
                "type": "player_joined_event",
                "player": self.role,
                "username": self.username,
            },
        )

    async def handle_move(self, data):
        if self.role == "spectator":
            await self.send_error("Spectators cannot make moves")
            return

        uci = data.get("uci")
        san = data.get("san")
        fen_after = data.get("fen")

        if not all([uci, san, fen_after]):
            await self.send_error("Move requires uci, san, and fen fields")
            return

        result = await self.save_move(uci, san, fen_after)
        if result.get("error"):
            await self.send_error(result["error"])
            return

        # Broadcast updated state to all (players + spectators)
        await self.channel_layer.group_send(
            self.room_group,
            {
                "type": "game_state_event",
                "fen": fen_after,
                "pgn": result["pgn"],
                "last_move": {"uci": uci, "san": san},
                "move_number": result["move_number"],
                "white_time": result["white_time"],
                "black_time": result["black_time"],
                "is_game_over": result["is_game_over"],
                "game_result": result.get("game_result"),
            },
        )

        if result["is_game_over"]:
            await self.channel_layer.group_send(
                self.room_group,
                {"type": "game_over_event", "result": result["game_result"]},
            )

    async def handle_resign(self, data):
        if self.role == "spectator":
            return

        winner = "black" if self.role == "white" else "white"
        await self.end_game(winner)
        await self.channel_layer.group_send(
            self.room_group,
            {
                "type": "game_over_event",
                "result": winner,
                "reason": "resignation",
                "resigned_by": self.role,
            },
        )

    async def handle_draw_offer(self, data):
        if self.role == "spectator":
            return
        opponent = "black" if self.role == "white" else "white"
        await self.channel_layer.group_send(
            self.room_group,
            {"type": "draw_offer_event", "offered_by": self.role, "to": opponent},
        )

    async def handle_draw_accept(self, data):
        if self.role == "spectator":
            return
        await self.end_game("draw")
        await self.channel_layer.group_send(
            self.room_group,
            {"type": "draw_result_event", "result": "draw", "accepted_by": self.role},
        )

    async def handle_draw_decline(self, data):
        await self.channel_layer.group_send(
            self.room_group,
            {"type": "draw_result_event", "result": "declined", "declined_by": self.role},
        )

    # ------------------------------------------------------------------ #
    #  Group event handlers (channel layer → websocket)                   #
    # ------------------------------------------------------------------ #

    async def game_state_event(self, event):
        await self.send(text_data=json.dumps({"type": "game_state", **event}))

    async def player_joined_event(self, event):
        await self.send(text_data=json.dumps({"type": "player_joined", **event}))

    async def player_left_event(self, event):
        await self.send(text_data=json.dumps({"type": "player_left", **event}))

    async def game_over_event(self, event):
        await self.send(text_data=json.dumps({"type": "game_over", **event}))

    async def draw_offer_event(self, event):
        await self.send(text_data=json.dumps({"type": "draw_offer", **event}))

    async def draw_result_event(self, event):
        await self.send(text_data=json.dumps({"type": "draw_result", **event}))

    # ------------------------------------------------------------------ #
    #  DB helpers (run in thread pool via database_sync_to_async)         #
    # ------------------------------------------------------------------ #

    @database_sync_to_async
    def get_game_state(self):
        try:
            room = Room.objects.get(id=self.room_id)
            game = room.game
            return {
                "fen": game.fen,
                "pgn": game.pgn,
                "white_player": game.white_player.username if game.white_player else None,
                "black_player": game.black_player.username if game.black_player else None,
                "white_time": game.white_time_remaining,
                "black_time": game.black_time_remaining,
                "result": game.result,
                "move_count": game.moves.count(),
            }
        except (Room.DoesNotExist, Game.DoesNotExist):
            return None

    @database_sync_to_async
    def assign_player_color(self):
        try:
            room = Room.objects.select_related("game").get(id=self.room_id)
        except Room.DoesNotExist:
            return {"error": "Room not found", "color": None}

        game, _ = Game.objects.get_or_create(room=room)

        if game.white_player == self.user:
            return {"error": None, "color": "white"}
        if game.black_player == self.user:
            return {"error": None, "color": "black"}

        if not game.white_player:
            game.white_player = self.user
            if not game.started_at:
                game.started_at = timezone.now()
                room.status = Room.STATUS_ACTIVE
                room.save(update_fields=["status"])
            game.save(update_fields=["white_player", "started_at"])
            return {"error": None, "color": "white"}

        if not game.black_player:
            game.black_player = self.user
            game.save(update_fields=["black_player"])
            return {"error": None, "color": "black"}

        return {"error": "Room is full", "color": None}

    @database_sync_to_async
    def save_move(self, uci, san, fen_after):
        try:
            game = Game.objects.get(room_id=self.room_id)
        except Game.DoesNotExist:
            return {"error": "Game not found"}

        move_number = game.moves.count() + 1
        Move.objects.create(
            game=game,
            move_number=move_number,
            san=san,
            uci=uci,
            fen_after=fen_after,
        )
        game.fen = fen_after

        # Rebuild PGN from moves
        moves = list(game.moves.order_by("move_number").values_list("san", flat=True))
        pgn_parts = []
        for i, m in enumerate(moves):
            if i % 2 == 0:
                pgn_parts.append(f"{i // 2 + 1}.")
            pgn_parts.append(m)
        game.pgn = " ".join(pgn_parts)
        game.save(update_fields=["fen", "pgn"])

        return {
            "pgn": game.pgn,
            "move_number": move_number,
            "white_time": game.white_time_remaining,
            "black_time": game.black_time_remaining,
            "is_game_over": game.result != Game.RESULT_ONGOING,
            "game_result": game.result if game.result != Game.RESULT_ONGOING else None,
        }

    @database_sync_to_async
    def end_game(self, result):
        from .utils import update_ratings
        try:
            game = Game.objects.select_related("white_player", "black_player").get(
                room_id=self.room_id
            )
            game.result = result
            game.ended_at = timezone.now()
            game.save(update_fields=["result", "ended_at"])

            game.room.status = Room.STATUS_FINISHED
            game.room.save(update_fields=["status"])

            update_ratings(game)
        except Game.DoesNotExist:
            pass

    async def send_error(self, message):
        await self.send(text_data=json.dumps({"type": "error", "message": message}))
