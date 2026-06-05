from django.contrib import admin
from .models import (
    Activity,
    Collection,
    CollectionItem,
    Comment,
    CommentLike,
    DailyQuizAttempt,
    Follow,
    Friendship,
    Item,
    Notification,
    Profile,
    Recommendation,
    Review,
    SavedReview,
)

for model in [
    Activity,
    Collection,
    CollectionItem,
    Comment,
    CommentLike,
    DailyQuizAttempt,
    Follow,
    Friendship,
    Item,
    Notification,
    Profile,
    Recommendation,
    Review,
    SavedReview,
]:
    admin.site.register(model)
