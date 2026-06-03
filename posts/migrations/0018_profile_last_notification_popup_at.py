from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("posts", "0017_performance_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="last_notification_popup_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
