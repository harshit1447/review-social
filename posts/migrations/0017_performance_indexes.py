from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("posts", "0016_alter_item_item_type"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="review",
            index=models.Index(fields=["-created_at"], name="review_created_idx"),
        ),
        migrations.AddIndex(
            model_name="review",
            index=models.Index(fields=["user", "-created_at"], name="review_user_created_idx"),
        ),
        migrations.AddIndex(
            model_name="review",
            index=models.Index(fields=["item", "-created_at"], name="review_item_created_idx"),
        ),
        migrations.AddIndex(
            model_name="saveditem",
            index=models.Index(fields=["user", "list_type"], name="saved_user_list_idx"),
        ),
        migrations.AddIndex(
            model_name="saveditem",
            index=models.Index(fields=["item", "list_type"], name="saved_item_list_idx"),
        ),
        migrations.AddIndex(
            model_name="follow",
            index=models.Index(fields=["follower"], name="follow_follower_idx"),
        ),
        migrations.AddIndex(
            model_name="follow",
            index=models.Index(fields=["following"], name="follow_following_idx"),
        ),
        migrations.AddIndex(
            model_name="friendship",
            index=models.Index(fields=["from_user"], name="friend_from_idx"),
        ),
        migrations.AddIndex(
            model_name="friendship",
            index=models.Index(fields=["to_user"], name="friend_to_idx"),
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(fields=["recipient", "is_read"], name="notif_recipient_read_idx"),
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(fields=["recipient", "-created_at"], name="notif_recipient_created_idx"),
        ),
        migrations.AddIndex(
            model_name="activity",
            index=models.Index(fields=["user", "-created_at"], name="activity_user_created_idx"),
        ),
        migrations.AddIndex(
            model_name="recommendation",
            index=models.Index(fields=["from_user", "item"], name="reco_from_item_idx"),
        ),
        migrations.AddIndex(
            model_name="recommendation",
            index=models.Index(fields=["to_user", "-created_at"], name="reco_to_created_idx"),
        ),
        migrations.AddIndex(
            model_name="item",
            index=models.Index(fields=["item_type", "title"], name="item_type_title_idx"),
        ),
    ]
