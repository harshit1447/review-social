# Generated manually to remove the old starter Post model.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("posts", "0003_friendship_recommendation_item_review"),
    ]

    operations = [
        migrations.DeleteModel(
            name="Post",
        ),
    ]
