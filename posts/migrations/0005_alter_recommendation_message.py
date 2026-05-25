# Generated manually for short recommendation notes.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("posts", "0004_delete_post"),
    ]

    operations = [
        migrations.AlterField(
            model_name="recommendation",
            name="message",
            field=models.CharField(blank=True, max_length=140),
        ),
    ]
