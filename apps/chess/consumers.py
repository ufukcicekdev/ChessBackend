import asyncio
import json
import logging
import chess
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from .models import Game, Move, Room

logger = logging.getLogger(__name__)

ABANDON_GRACE_SECONDS = 60

# Fallback in-process dict used only when Redis is unavailable (single-instance mode).
_pending_abandons: dict[tuple, asyncio.Task] = {}


def _get_redis():
    try:
        import redis as redis_lib
        from django.conf import settings
        r = redis_lib.from_url(settings.REDIS_URL or "", decode_responses=True)
        r.ping()
        return r
    except Exception:
        return None


def _schedule_abandon_sync(room_id: str, color: str):
    """Schedule a Celery abandon task; return True if scheduled via Redis."""
    r = _get_redis()
    if not r:
        return False
    from .tasks import abandon_game_task
    sentinel = f"abandon:{room_id}:{color}"
    task_key = f"abandon_task:{room_id}:{color}"
    r.setex(sentinel, ABANDON_GRACE_SECONDS + 30, "1")
    result = abandon_game_task.apply_async(
        args=[room_id, color],
        countdown=ABANDON_GRACE_SECONDS,
    )
    r.setex(task_key, ABANDON_GRACE_SECONDS + 30, result.id)
    return True


def _cancel_abandon_sync(room_id: str, color: str):
    """Revoke the pending Celery abandon task; return True if one was cancelled."""
    r = _get_redis()
    if not r:
        return False
    sentinel = f"abandon:{room_id}:{color}"
    task_key = f"abandon_task:{room_id}:{color}"
    task_id = r.get(task_key)
    if not task_id:
        return False
    r.delete(sentinel)
    r.delete(task_key)
    from config.celery import app as celery_app
    celery_app.control.revoke(task_id, terminate=False)
    return True


class ChessConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for a chess room.

    URL: ws://.../ws/chess/<room_id>/?token=<jwt>

    Message types sent by client:
      - join:       Player joins the room and picks a color.
      - move:       Player submits a move.
      - time_loss:  Client reports local clock hit 0 (server validates + ends game).
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
            if await self.is_game_ongoing():
                loop = asyncio.get_event_loop()
                # Always start in-process timer (works even without Celery worker)
                key = (self.room_id, self.role)
                if key not in _pending_abandons:
                    task = asyncio.create_task(self._abandon_after_grace(key))
                    _pending_abandons[key] = task
                # Also try Celery for multi-instance setups (best-effort)
                await loop.run_in_executor(
                    None, _schedule_abandon_sync, str(self.room_id), self.role
                )

    async def receive(self, text_data):
        if len(text_data) > 2048:
            await self.send_error("Message too large")
            return
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send_error("Invalid JSON")
            return

        msg_type = data.get("type")
        handlers = {
            "join": self.handle_join,
            "move": self.handle_move,
            "time_loss": self.handle_time_loss,
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

        # Cancel pending abandon timer if this player is reconnecting
        loop = asyncio.get_event_loop()
        cancelled_via_celery = await loop.run_in_executor(
            None, _cancel_abandon_sync, str(self.room_id), self.role
        )
        # Also check in-process fallback dict
        in_process_key = (self.room_id, self.role)
        in_process_task = _pending_abandons.pop(in_process_key, None)
        if in_process_task:
            in_process_task.cancel()

        if cancelled_via_celery or in_process_task:
            await self.channel_layer.group_send(
                self.room_group,
                {"type": "player_reconnected_event", "player": self.role, "username": self.username},
            )
            return

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
            logger.warning("Move rejected room=%s user=%s error=%s uci=%s", self.room_id, getattr(self.user, 'username', '?'), result["error"], uci)
            await self.send_error(result["error"])
            return

        logger.info("Move accepted room=%s user=%s uci=%s group=%s", self.room_id, getattr(self.user, 'username', '?'), uci, self.room_group)
        extras = await self.get_player_rating_extras()

        # Broadcast updated state to all (players + spectators)
        await self.channel_layer.group_send(
            self.room_group,
            {
                "type": "game_state_event",
                "fen": result["fen"],
                "pgn": result["pgn"],
                "last_move": {"uci": uci, "san": san},
                "move_number": result["move_number"],
                "white_time": result["white_time"],
                "black_time": result["black_time"],
                "white_rating": extras.get("white_rating"),
                "black_rating": extras.get("black_rating"),
                "white_title": extras.get("white_title"),
                "black_title": extras.get("black_title"),
                "is_check": result.get("is_check"),
                "is_game_over": result["is_game_over"],
                "game_result": result.get("game_result"),
            },
        )

        if result["is_game_over"]:
            await self.channel_layer.group_send(
                self.room_group,
                {"type": "game_over_event", "result": result["game_result"]},
            )

    async def handle_time_loss(self, data):
        if self.role == "spectator":
            return

        loser = data.get("loser")  # "white" | "black"
        if loser not in ("white", "black"):
            await self.send_error("time_loss requires loser: white|black")
            return
        if loser != self.role:
            await self.send_error("time_loss loser must match your color")
            return

        ended = await self.end_game_on_timeout(loser)
        if not ended.get("ok"):
            await self.send_error(ended.get("error", "Unable to end game on time"))
            return

        winner = "black" if loser == "white" else "white"
        await self.channel_layer.group_send(
            self.room_group,
            {
                "type": "game_over_event",
                "result": winner,
                "reason": "timeout",
                "loser": loser,
            },
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
        # `event` includes Channels' internal "type" key (e.g. "game_state_event").
        # Ensure the websocket message type is the public one ("game_state").
        payload = {k: v for k, v in event.items() if k != "type"}
        payload["type"] = "game_state"
        logger.info("Sending game_state to channel=%s fen=%s", self.channel_name[:20], payload.get("fen", "")[:30])
        await self.send(text_data=json.dumps(payload))

    async def player_joined_event(self, event):
        payload = {k: v for k, v in event.items() if k != "type"}
        payload["type"] = "player_joined"
        await self.send(text_data=json.dumps(payload))

    async def player_left_event(self, event):
        payload = {k: v for k, v in event.items() if k != "type"}
        payload["type"] = "player_left"
        await self.send(text_data=json.dumps(payload))

    async def game_over_event(self, event):
        payload = {k: v for k, v in event.items() if k != "type"}
        payload["type"] = "game_over"
        await self.send(text_data=json.dumps(payload))

    async def draw_offer_event(self, event):
        payload = {k: v for k, v in event.items() if k != "type"}
        payload["type"] = "draw_offer"
        await self.send(text_data=json.dumps(payload))

    async def draw_result_event(self, event):
        payload = {k: v for k, v in event.items() if k != "type"}
        payload["type"] = "draw_result"
        await self.send(text_data=json.dumps(payload))

    async def player_reconnected_event(self, event):
        payload = {k: v for k, v in event.items() if k != "type"}
        payload["type"] = "player_reconnected"
        await self.send(text_data=json.dumps(payload))

    # ------------------------------------------------------------------ #
    #  Abandon grace-period                                               #
    # ------------------------------------------------------------------ #

    async def _abandon_after_grace(self, key: tuple):
        await asyncio.sleep(ABANDON_GRACE_SECONDS)
        _pending_abandons.pop(key, None)
        _, color = key
        winner = "black" if color == "white" else "white"
        await self.end_game(winner)
        await self.channel_layer.group_send(
            self.room_group,
            {"type": "game_over_event", "result": winner, "reason": "abandonment"},
        )

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
                "white_rating": game.white_player.rating if game.white_player else None,
                "black_rating": game.black_player.rating if game.black_player else None,
                "white_title": game.white_player.title if game.white_player else None,
                "black_title": game.black_player.title if game.black_player else None,
                "white_time": game.white_time_remaining,
                "black_time": game.black_time_remaining,
                "is_game_over": game.result != Game.RESULT_ONGOING,
                "game_result": game.result if game.result != Game.RESULT_ONGOING else None,
                "result": game.result,
                "move_count": game.moves.count(),
            }
        except (Room.DoesNotExist, Game.DoesNotExist):
            return None

    @database_sync_to_async
    def get_player_rating_extras(self):
        try:
            game = Game.objects.select_related("white_player", "black_player").get(room_id=self.room_id)
        except Game.DoesNotExist:
            return {}
        return {
            "white_rating": game.white_player.rating if game.white_player else None,
            "black_rating": game.black_player.rating if game.black_player else None,
            "white_title": game.white_player.title if game.white_player else None,
            "black_title": game.black_player.title if game.black_player else None,
        }

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
            # Initialize clocks from room time control when the game actually starts.
            if game.white_time_remaining == 600 and game.black_time_remaining == 600:
                game.white_time_remaining = room.time_control
                game.black_time_remaining = room.time_control
            game.last_move_at = timezone.now()
            game.save(update_fields=["white_player", "started_at", "white_time_remaining", "black_time_remaining", "last_move_at"])
            return {"error": None, "color": "white"}

        if not game.black_player:
            game.black_player = self.user
            game.last_move_at = timezone.now()
            game.save(update_fields=["black_player", "last_move_at"])
            return {"error": None, "color": "black"}

        return {"error": "Room is full", "color": None}

    @database_sync_to_async
    def save_move(self, uci, san, fen_after):
        try:
            game = Game.objects.select_related("room").get(room_id=self.room_id)
        except Game.DoesNotExist:
            return {"error": "Game not found"}

        if game.result != Game.RESULT_ONGOING:
            return {"error": "Game is already over"}

        if not game.white_player or not game.black_player:
            return {"error": "Waiting for opponent"}

        room = game.room
        now = timezone.now()

        board = chess.Board(game.fen)
        moving_color = chess.WHITE if board.turn else chess.BLACK

        if self.user != (game.white_player if moving_color == chess.WHITE else game.black_player):
            return {"error": "Not your turn"}

        try:
            move = chess.Move.from_uci(uci)
        except ValueError:
            return {"error": "Invalid UCI"}

        if move not in board.legal_moves:
            return {"error": "Illegal move"}

        # Apply elapsed time to the side that is moving *before* applying the move.
        last_ts = game.last_move_at or game.started_at or now
        elapsed = max(0, int((now - last_ts).total_seconds()))
        inc = int(room.increment or 0)

        if moving_color == chess.WHITE:
            game.white_time_remaining = max(0, int(game.white_time_remaining) - elapsed + inc)
            if game.white_time_remaining <= 0:
                game.white_time_remaining = 0
                game.result = Game.RESULT_BLACK
                game.ended_at = now
                game.last_move_at = now
                game.save(
                    update_fields=[
                        "white_time_remaining",
                        "result",
                        "ended_at",
                        "last_move_at",
                    ]
                )
                game.room.status = Room.STATUS_FINISHED
                game.room.save(update_fields=["status"])
                from .tasks import update_ratings_task
                update_ratings_task.delay(str(game.id))
                return {
                    "fen": game.fen,
                    "pgn": game.pgn,
                    "move_number": game.moves.count(),
                    "white_time": game.white_time_remaining,
                    "black_time": game.black_time_remaining,
                    "is_check": False,
                    "is_game_over": True,
                    "game_result": game.result,
                }
        else:
            game.black_time_remaining = max(0, int(game.black_time_remaining) - elapsed + inc)
            if game.black_time_remaining <= 0:
                game.black_time_remaining = 0
                game.result = Game.RESULT_WHITE
                game.ended_at = now
                game.last_move_at = now
                game.save(
                    update_fields=[
                        "black_time_remaining",
                        "result",
                        "ended_at",
                        "last_move_at",
                    ]
                )
                game.room.status = Room.STATUS_FINISHED
                game.room.save(update_fields=["status"])
                from .tasks import update_ratings_task
                update_ratings_task.delay(str(game.id))
                return {
                    "fen": game.fen,
                    "pgn": game.pgn,
                    "move_number": game.moves.count(),
                    "white_time": game.white_time_remaining,
                    "black_time": game.black_time_remaining,
                    "is_check": False,
                    "is_game_over": True,
                    "game_result": game.result,
                }

        san_server = board.san(move)
        if san_server != san:
            return {"error": "SAN mismatch"}

        board.push(move)
        fen_server = board.fen()

        if fen_server != fen_after:
            return {"error": "FEN mismatch"}

        move_number = game.moves.count() + 1
        Move.objects.create(
            game=game,
            move_number=move_number,
            san=san_server,
            uci=uci,
            fen_after=fen_server,
        )
        game.fen = fen_server
        game.last_move_at = now

        # Rebuild PGN from moves
        moves = list(game.moves.order_by("move_number").values_list("san", flat=True))
        pgn_parts = []
        for i, m in enumerate(moves):
            if i % 2 == 0:
                pgn_parts.append(f"{i // 2 + 1}.")
            pgn_parts.append(m)
        game.pgn = " ".join(pgn_parts)

        outcome = board.outcome(claim_draw=True)
        if outcome and outcome.winner is not None:
            game.result = Game.RESULT_WHITE if outcome.winner == chess.WHITE else Game.RESULT_BLACK
            game.ended_at = now
        elif outcome and outcome.winner is None and outcome.termination in (
            chess.Termination.STALEMATE,
            chess.Termination.INSUFFICIENT_MATERIAL,
            chess.Termination.FIFTY_MOVES,
            chess.Termination.THREEFOLD_REPETITION,
            chess.Termination.SEVENTYFIVE_MOVES,
            chess.Termination.FIVEFOLD_REPETITION,
        ):
            game.result = Game.RESULT_DRAW
            game.ended_at = now

        game.save(
            update_fields=[
                "fen",
                "pgn",
                "white_time_remaining",
                "black_time_remaining",
                "last_move_at",
                "result",
                "ended_at",
            ]
        )

        if game.result != Game.RESULT_ONGOING:
            game.room.status = Room.STATUS_FINISHED
            game.room.save(update_fields=["status"])
            from .tasks import update_ratings_task
            update_ratings_task.delay(str(game.id))

        return {
            "fen": game.fen,
            "pgn": game.pgn,
            "move_number": move_number,
            "white_time": game.white_time_remaining,
            "black_time": game.black_time_remaining,
            "is_check": bool(board.is_check()) if game.result == Game.RESULT_ONGOING else False,
            "is_game_over": game.result != Game.RESULT_ONGOING,
            "game_result": game.result if game.result != Game.RESULT_ONGOING else None,
        }

    @database_sync_to_async
    def end_game(self, result):
        try:
            game = Game.objects.select_related("white_player", "black_player").get(
                room_id=self.room_id
            )
            if game.result != Game.RESULT_ONGOING:
                return
            game.result = result
            game.ended_at = timezone.now()
            game.save(update_fields=["result", "ended_at"])

            game.room.status = Room.STATUS_FINISHED
            game.room.save(update_fields=["status"])

            from .tasks import update_ratings_task
            update_ratings_task.delay(str(game.id))
        except Game.DoesNotExist:
            pass

    @database_sync_to_async
    def end_game_on_timeout(self, loser_role: str):
        try:
            game = Game.objects.select_related("white_player", "black_player", "room").get(
                room_id=self.room_id
            )
        except Game.DoesNotExist:
            return {"ok": False, "error": "Game not found"}

        if game.result != Game.RESULT_ONGOING:
            return {"ok": False, "error": "Game is already over"}

        if not game.white_player or not game.black_player:
            return {"ok": False, "error": "Waiting for opponent"}

        now = timezone.now()
        last_ts = game.last_move_at or game.started_at or now
        elapsed = max(0, int((now - last_ts).total_seconds()))

        # Determine whose clock should be running based on FEN side-to-move.
        board = chess.Board(game.fen)
        active = "white" if board.turn == chess.WHITE else "black"

        if loser_role != active:
            return {"ok": False, "error": "Timeout claim does not match active side"}

        if active == "white":
            remaining = max(0, int(game.white_time_remaining) - elapsed)
            if remaining > 0:
                return {"ok": False, "error": "Clock not exhausted"}
            game.white_time_remaining = 0
        else:
            remaining = max(0, int(game.black_time_remaining) - elapsed)
            if remaining > 0:
                return {"ok": False, "error": "Clock not exhausted"}
            game.black_time_remaining = 0

        winner = "black" if active == "white" else "white"
        game.result = winner
        game.ended_at = now
        game.last_move_at = now
        game.save(update_fields=["white_time_remaining", "black_time_remaining", "result", "ended_at", "last_move_at"])

        game.room.status = Room.STATUS_FINISHED
        game.room.save(update_fields=["status"])

        from .tasks import update_ratings_task
        update_ratings_task.delay(str(game.id))
        return {"ok": True}

    @database_sync_to_async
    def is_game_ongoing(self):
        try:
            game = Game.objects.get(room_id=self.room_id)
            return (
                game.result == Game.RESULT_ONGOING
                and game.white_player_id is not None
                and game.black_player_id is not None
            )
        except Game.DoesNotExist:
            return False

    async def send_error(self, message):
        await self.send(text_data=json.dumps({"type": "error", "message": message}))
