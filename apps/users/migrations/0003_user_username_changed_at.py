from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0002_user_iban_user_wallet_balance"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="username_changed_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
    ]
