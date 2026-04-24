# placeholder — index'ler zaten DB'de mevcut, bu migration boş
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("chess", "0009_add_rating_change_fields"),
    ]

    operations = []
