from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("posts", "0010_item_rating_defaults"),
    ]

    operations = [
        migrations.AlterField(
            model_name="item",
            name="book_rating",
            field=models.CharField(blank=True, default="", max_length=20, null=True),
        ),
        migrations.AlterField(
            model_name="item",
            name="book_rating_source",
            field=models.CharField(blank=True, default="", max_length=40, null=True),
        ),
        migrations.AlterField(
            model_name="item",
            name="imdb_rating",
            field=models.CharField(blank=True, default="", max_length=20, null=True),
        ),
        migrations.AlterField(
            model_name="item",
            name="rotten_tomatoes_rating",
            field=models.CharField(blank=True, default="", max_length=20, null=True),
        ),
    ]
