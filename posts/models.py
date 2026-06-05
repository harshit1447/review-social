from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


class Item(models.Model):
    TYPE_CHOICES = [
        ("movie", "Movie"),
        ("book", "Book"),
        ("series", "Series"),
        ("podcast", "Podcast"),
        ("experience", "Experience"),
    ]

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    image_url = models.URLField(blank=True)
    release_year = models.CharField(max_length=10, blank=True)
    creator_name = models.CharField(max_length=255, blank=True)
    cast_names = models.TextField(blank=True, default="")
    producer_name = models.CharField(max_length=255, blank=True, default="")
    imdb_rating = models.CharField(max_length=20, blank=True, null=True, default="")
    rotten_tomatoes_rating = models.CharField(max_length=20, blank=True, null=True, default="")
    book_rating = models.CharField(max_length=20, blank=True, null=True, default="")
    book_rating_source = models.CharField(max_length=40, blank=True, null=True, default="")
    external_source = models.CharField(max_length=30, blank=True)
    external_id = models.CharField(max_length=80, blank=True)
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


class ReviewLike(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="review_likes",
    )
    review = models.ForeignKey(
        Review,
        on_delete=models.CASCADE,
        related_name="likes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "review"],
                name="unique_review_like",
            )
        ]

    def __str__(self):
        return f"{self.user} likes review {self.review_id}"


class SavedItem(models.Model):
    LIST_CHOICES = [
        ("watchlist", "Watchlist"),
        ("readlist", "Readlist"),
        ("favorites", "Favorites"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="saved_items",
    )
    item = models.ForeignKey(
        Item,
        on_delete=models.CASCADE,
        related_name="saved_entries",
    )
    list_type = models.CharField(max_length=20, choices=LIST_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "item", "list_type"],
                name="unique_saved_item_per_list",
            )
        ]

    def __str__(self):
        return f"{self.user} saved {self.item} in {self.list_type}"


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    profile_photo = models.FileField(upload_to="profiles/photos/", blank=True)
    cover_image = models.FileField(upload_to="profiles/covers/", blank=True)
    bio = models.TextField(blank=True)
    location = models.CharField(max_length=120, blank=True)
    website = models.URLField(blank=True)
    favorite_categories = models.CharField(max_length=255, blank=True)
    last_notification_popup_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username}'s profile"


class Follow(models.Model):
    follower = models.ForeignKey(User, on_delete=models.CASCADE, related_name="following_relationships")
    following = models.ForeignKey(User, on_delete=models.CASCADE, related_name="follower_relationships")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["follower", "following"], name="unique_follow"),
            models.CheckConstraint(condition=~models.Q(follower=models.F("following")), name="no_self_follow"),
        ]

    def __str__(self):
        return f"{self.follower} follows {self.following}"


class Collection(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="collections")
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    is_public = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.title


class CollectionItem(models.Model):
    collection = models.ForeignKey(Collection, on_delete=models.CASCADE, related_name="items")
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="collection_entries")
    note = models.CharField(max_length=180, blank=True)
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position", "created_at"]
        constraints = [
            models.UniqueConstraint(fields=["collection", "item"], name="unique_item_per_collection")
        ]

    def __str__(self):
        return f"{self.item} in {self.collection}"


class Activity(models.Model):
    REVIEW_POSTED = "review_posted"
    REVIEW_LIKED = "review_liked"
    USER_FOLLOWED = "user_followed"
    RECOMMENDED = "recommended"
    COMMENTED = "commented"
    COLLECTION_CREATED = "collection_created"

    TYPE_CHOICES = [
        (REVIEW_POSTED, "Posted review"),
        (REVIEW_LIKED, "Liked review"),
        (USER_FOLLOWED, "Followed user"),
        (RECOMMENDED, "Recommended"),
        (COMMENTED, "Commented"),
        (COLLECTION_CREATED, "Created collection"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="activities")
    activity_type = models.CharField(max_length=32, choices=TYPE_CHOICES)
    review = models.ForeignKey(Review, on_delete=models.CASCADE, blank=True, null=True, related_name="activities")
    target_user = models.ForeignKey(User, on_delete=models.CASCADE, blank=True, null=True, related_name="targeted_activities")
    collection = models.ForeignKey(Collection, on_delete=models.CASCADE, blank=True, null=True, related_name="activities")
    message = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.message or f"{self.user} {self.activity_type}"


class Comment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="comments")
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name="comments")
    parent = models.ForeignKey("self", on_delete=models.CASCADE, blank=True, null=True, related_name="replies")
    body = models.TextField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.user} on review {self.review_id}"


class CommentLike(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="comment_likes")
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name="likes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "comment"], name="unique_comment_like")
        ]

    def __str__(self):
        return f"{self.user} likes comment {self.comment_id}"


class Notification(models.Model):
    FOLLOW = "follow"
    LIKE = "like"
    COMMENT = "comment"
    REPLY = "reply"

    TYPE_CHOICES = [
        (FOLLOW, "Follow"),
        (LIKE, "Like"),
        (COMMENT, "Comment"),
        (REPLY, "Reply"),
    ]

    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    actor = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications_sent")
    notification_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    review = models.ForeignKey(Review, on_delete=models.CASCADE, blank=True, null=True, related_name="notifications")
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, blank=True, null=True, related_name="notifications")
    message = models.CharField(max_length=255)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.message


class SavedReview(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="saved_reviews")
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name="saved_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "review"], name="unique_saved_review")
        ]

    def __str__(self):
        return f"{self.user} saved review {self.review_id}"


class DailyQuizAttempt(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="daily_quiz_attempts")
    quiz_date = models.DateField()
    score = models.PositiveSmallIntegerField(default=0)
    total_questions = models.PositiveSmallIntegerField(default=6)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-quiz_date", "-score", "updated_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "quiz_date"], name="unique_daily_quiz_attempt")
        ]

    def __str__(self):
        return f"{self.user} scored {self.score}/{self.total_questions} on {self.quiz_date}"


@receiver(post_save, sender=User)
def ensure_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance)
