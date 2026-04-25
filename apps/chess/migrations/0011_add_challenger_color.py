from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("chess", "0010_add_room_to_match"),
    ]

    operations = [
        migrations.AddField(
            model_name="challenge",
            name="challenger_color",
            field=models.CharField(default="random", max_length=10),
        ),
    ]
