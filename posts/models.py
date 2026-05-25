from django.db import models
from django.contrib.auth.models import User


class Item(models.Model):
    TYPE_CHOICES = [
        ("movie", "Movie"),
        ("book", "Book"),
        ("series", "Series"),
    ]

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    item_type = models.CharField(max_length=20, choices=TYPE_CHOICES)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class Review(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    item = models.ForeignKey(
        Item,
        on_delete=models.CASCADE,
        related_name="reviews"
    )

    rating = models.IntegerField()

    review_text = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} reviewed {self.item}"


class Friendship(models.Model):
    from_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="friendships_sent",
    )
    to_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="friendships_received",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["from_user", "to_user"],
                name="unique_friendship",
            ),
            models.CheckConstraint(
                condition=~models.Q(from_user=models.F("to_user")),
                name="no_self_friendship",
            ),
        ]

    def __str__(self):
        return f"{self.from_user} follows {self.to_user}"


class Recommendation(models.Model):
    from_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="recommendations_sent",
    )
    to_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="recommendations_received",
    )
    item = models.ForeignKey(
        Item,
        on_delete=models.CASCADE,
        related_name="recommendations",
    )
    message = models.CharField(max_length=140, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.from_user} recommended {self.item} to {self.to_user}"
