from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("posts", "0018_profile_last_notification_popup_at"),
    ]

    operations = [
        migrations.CreateModel(
            name="DailyQuizAttempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quiz_date", models.DateField()),
                ("score", models.PositiveSmallIntegerField(default=0)),
                ("total_questions", models.PositiveSmallIntegerField(default=6)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="daily_quiz_attempts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-quiz_date", "-score", "updated_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="dailyquizattempt",
            constraint=models.UniqueConstraint(
                fields=("user", "quiz_date"),
                name="unique_daily_quiz_attempt",
            ),
        ),
    ]
