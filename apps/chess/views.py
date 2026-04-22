import stripe
from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from .models import Room, Game, Donation
from .serializers import RoomSerializer, RoomCreateSerializer, GameSerializer, DonationSerializer

stripe.api_key = settings.STRIPE_SECRET_KEY


class RoomListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return RoomCreateSerializer
        return RoomSerializer

    def get_queryset(self):
        qs = Room.objects.select_related("created_by", "game").filter(is_public=True)
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    def create(self, request, *args, **kwargs):
        serializer = RoomCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        room = serializer.save()
        return Response(RoomSerializer(room).data, status=status.HTTP_201_CREATED)


class RoomDetailView(generics.RetrieveAPIView):
    queryset = Room.objects.select_related("created_by", "game")
    serializer_class = RoomSerializer
    lookup_field = "id"
    permission_classes = [permissions.AllowAny]


class GameHistoryView(generics.ListAPIView):
    serializer_class = GameSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        username = self.kwargs.get("username")
        return Game.objects.filter(
            result__in=["white", "black", "draw"]
        ).filter(
            white_player__username=username
        ) | Game.objects.filter(
            result__in=["white", "black", "draw"]
        ).filter(
            black_player__username=username
        ).order_by("-created_at")[:50]


class GameDetailView(generics.RetrieveAPIView):
    queryset = Game.objects.prefetch_related("moves").select_related("white_player", "black_player")
    serializer_class = GameSerializer
    lookup_field = "id"
    permission_classes = [permissions.AllowAny]


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def create_donation(request, room_id):
    room = get_object_or_404(Room, id=room_id)
    serializer = DonationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    amount_cents = int(serializer.validated_data["amount"] * 100)
    currency = serializer.validated_data.get("currency", "usd").lower()

    try:
        intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency=currency,
            metadata={"room_id": str(room_id)},
        )
        donation = Donation.objects.create(
            room=room,
            donor=request.user if request.user.is_authenticated else None,
            amount=serializer.validated_data["amount"],
            currency=currency.upper(),
            message=serializer.validated_data.get("message", ""),
            stripe_payment_intent=intent.id,
            status="pending",
        )
        return Response(
            {
                "client_secret": intent.client_secret,
                "donation_id": str(donation.id),
            },
            status=status.HTTP_201_CREATED,
        )
    except stripe.error.StripeError as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        return Response(status=status.HTTP_400_BAD_REQUEST)

    if event["type"] == "payment_intent.succeeded":
        intent_id = event["data"]["object"]["id"]
        Donation.objects.filter(stripe_payment_intent=intent_id).update(status="completed")

    return Response({"status": "ok"})
