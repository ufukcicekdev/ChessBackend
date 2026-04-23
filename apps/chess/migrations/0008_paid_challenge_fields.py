from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("chess", "0007_challenge"),
    ]

    operations = [
        # PlatformSettings: paid challenge config
        migrations.AddField(
            model_name="platformsettings",
            name="paid_challenges_enabled",
            field=models.BooleanField(default=False, help_text="Ücretli challenge sistemini aktif eder."),
        ),
        migrations.AddField(
            model_name="platformsettings",
            name="challenge_fee_percent",
            field=models.DecimalField(decimal_places=2, default=10, max_digits=5, help_text="Kazançtan alınan platform komisyonu (%)"),
        ),
        migrations.AddField(
            model_name="platformsettings",
            name="challenge_min_wager",
            field=models.DecimalField(decimal_places=2, default=1.0, max_digits=8, help_text="Minimum bahis miktarı (USD)"),
        ),
        migrations.AddField(
            model_name="platformsettings",
            name="challenge_max_wager",
            field=models.DecimalField(decimal_places=2, default=100.0, max_digits=8, help_text="Maksimum bahis miktarı (USD)"),
        ),
        # Challenge: wager fields
        migrations.AddField(
            model_name="challenge",
            name="wager_amount",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True),
        ),
        migrations.AddField(
            model_name="challenge",
            name="challenger_payment_intent",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="challenge",
            name="challenged_payment_intent",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="challenge",
            name="challenger_paid",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="challenge",
            name="challenged_paid",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="challenge",
            name="payout_intent",
            field=models.CharField(blank=True, max_length=200),
        ),
    ]
