from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("posts", "0008_item_creator_name_item_external_id_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="item",
            name="book_rating",
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name="item",
            name="book_rating_source",
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AddField(
            model_name="item",
            name="imdb_rating",
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name="item",
            name="rotten_tomatoes_rating",
            field=models.CharField(blank=True, max_length=20),
        ),
    ]
