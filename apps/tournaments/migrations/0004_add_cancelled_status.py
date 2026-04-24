from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tournaments", "0003_add_room_to_match"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tournament",
            name="status",
            field=models.CharField(
                choices=[
                    ("registration", "Registration"),
                    ("active", "Active"),
                    ("finished", "Finished"),
                    ("cancelled", "Cancelled"),
                ],
                default="registration",
                max_length=20,
            ),
        ),
    ]
