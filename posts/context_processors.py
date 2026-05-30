import os

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.sites.models import Site


def _google_enabled_from_social_app() -> bool:
    try:
        from allauth.socialaccount.models import SocialApp
    except Exception:
        return False

    try:
        current_site = Site.objects.get_current()
    except Exception:
        return False

    return SocialApp.objects.filter(provider="google", sites=current_site).exists()


def auth_options(request):
    social_counts = {
        "sidebar_review_count": 0,
        "sidebar_followers_count": 0,
        "sidebar_following_count": 0,
        "unread_notification_count": 0,
        "recommend_friends": [],
    }
    if getattr(request, "user", None) and request.user.is_authenticated:
        try:
            from .models import Follow, Friendship, Notification, Review

            friend_ids = set(
                Follow.objects.filter(follower=request.user).values_list("following_id", flat=True)
            ) | set(
                Friendship.objects.filter(from_user=request.user).values_list("to_user_id", flat=True)
            )
            recommend_friends = User.objects.filter(id__in=friend_ids).order_by(
                "first_name",
                "username",
            )[:50]
            social_counts = {
                "sidebar_review_count": Review.objects.filter(user=request.user).count(),
                "sidebar_followers_count": Follow.objects.filter(following=request.user).count()
                or Friendship.objects.filter(to_user=request.user).count(),
                "sidebar_following_count": Follow.objects.filter(follower=request.user).count()
                or Friendship.objects.filter(from_user=request.user).count(),
                "unread_notification_count": Notification.objects.filter(
                    recipient=request.user,
                    is_read=False,
                ).count(),
                "recommend_friends": recommend_friends,
            }
        except Exception:
            pass

    env_configured = bool(
        os.environ.get("GOOGLE_CLIENT_ID")
        and os.environ.get("GOOGLE_CLIENT_SECRET")
    )
    settings_configured = bool(
        settings.SOCIALACCOUNT_PROVIDERS.get("google", {}).get("APPS")
    )

    return {
        "google_auth_enabled": env_configured
        or settings_configured
        or _google_enabled_from_social_app()
        ,
        **social_counts,
    }
