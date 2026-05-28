from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("posts", "0011_item_rating_fields_nullable"),
    ]

    operations = [
        migrations.AddField(
            model_name="item",
            name="cast_names",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="item",
            name="producer_name",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
    ]
