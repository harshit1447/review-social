import os

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.core.cache import cache
from django.templatetags.static import static
from django.utils import timezone
from django.urls import reverse


def _google_enabled_from_social_app() -> bool:
    cached = cache.get("google_auth_enabled_from_social_app")
    if cached is not None:
        return cached

    try:
        from allauth.socialaccount.models import SocialApp
    except Exception:
        return False

    try:
        current_site = Site.objects.get_current()
    except Exception:
        return False

    enabled = SocialApp.objects.filter(provider="google", sites=current_site).exists()
    cache.set("google_auth_enabled_from_social_app", enabled, 300)
    return enabled


def _display_name(user):
    return user.get_full_name() or user.username


def _notification_target(notification):
    if notification.review_id and notification.review and notification.review.item:
        return {
            "url": f"{reverse('item_reviews', args=[notification.review.item.title])}#review-{notification.review_id}",
            "label": "View review",
        }
    if notification.actor_id:
        return {
            "url": reverse("user_profile", args=[notification.actor.username]),
            "label": "View profile",
        }
    return {"url": reverse("notifications"), "label": "Open notifications"}


def _login_notification_toasts(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return []

    login_marker = user.last_login.isoformat() if user.last_login else "active"
    session_key = f"login_notification_toasts_seen:{user.id}:{login_marker}"
    user_session_key = f"login_notification_toasts_seen_for_user:{user.id}"
    if request.session.get(session_key) or request.session.get(user_session_key):
        return []

    try:
        from .models import Notification, Profile

        profile, _ = Profile.objects.get_or_create(user=user)
        cutoff = profile.last_notification_popup_at or user.date_joined
        notifications = list(
            Notification.objects.filter(
                recipient=user,
                created_at__gt=cutoff,
            )
            .select_related("actor", "review", "review__item")
            .order_by("-created_at")[:5]
        )
        request.session[session_key] = True
        request.session[user_session_key] = True
        request.session.modified = True
        profile.last_notification_popup_at = timezone.now()
        profile.save(update_fields=["last_notification_popup_at"])
    except Exception:
        return []

    rows = []
    for notification in notifications:
        target = _notification_target(notification)
        rows.append(
            {
                "actor": _display_name(notification.actor),
                "message": notification.message,
                "url": target["url"],
                "label": target["label"],
            }
        )
    return rows


def _daily_quiz_prompt(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return None
    resolver_match = getattr(request, "resolver_match", None)
    if resolver_match and resolver_match.url_name == "daily_quiz":
        return None

    today = timezone.localdate().isoformat()
    try:
        from .models import DailyQuizAttempt

        if DailyQuizAttempt.objects.filter(user=user, quiz_date=today).exists():
            return None
    except Exception:
        pass

    session_key = f"daily_quiz_prompt_seen:{user.id}:{today}"
    if request.session.get(session_key):
        return None

    request.session[session_key] = True
    request.session.modified = True
    return {
        "date": today,
        "url": reverse("daily_quiz"),
    }


def auth_options(request):
    social_counts = {
        "sidebar_review_count": 0,
        "sidebar_followers_count": 0,
        "sidebar_following_count": 0,
        "unread_notification_count": 0,
        "recommend_friends": [],
    }
    login_notification_toasts = _login_notification_toasts(request)
    daily_quiz_prompt = _daily_quiz_prompt(request)
    if getattr(request, "user", None) and request.user.is_authenticated:
        cache_key = f"auth_options:{request.user.id}"
        cached_counts = cache.get(cache_key)
        if cached_counts is not None:
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
                or _google_enabled_from_social_app(),
                "login_notification_toasts": login_notification_toasts,
                "daily_quiz_prompt": daily_quiz_prompt,
                **cached_counts,
            }
        try:
            from .models import Follow, Friendship, Notification, Review

            friend_ids = set(
                Follow.objects.filter(follower=request.user).values_list("following_id", flat=True)
            ) | set(
                Friendship.objects.filter(from_user=request.user).values_list("to_user_id", flat=True)
            )
            recommend_friends = list(User.objects.filter(id__in=friend_ids).select_related("profile").order_by(
                "first_name",
                "username",
            )[:50])
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
            cache.set(cache_key, social_counts, 60)
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
        "login_notification_toasts": login_notification_toasts,
        "daily_quiz_prompt": daily_quiz_prompt,
        **social_counts,
    }


def seo_defaults(request):
    site_url = getattr(settings, "PUBLIC_SITE_URL", "https://www.revue.social").rstrip("/")
    path = getattr(request, "path", "/") or "/"
    canonical = f"{site_url}{path}"
    default_title = "Revue - Social reviews from people whose taste you trust"
    default_description = (
        "Discover movies, series, and books through reviews, recommendations, "
        "and people who share your taste."
    )
    return {
        "seo_site_name": "Revue",
        "seo_site_url": site_url,
        "seo_title": default_title,
        "seo_description": default_description,
        "seo_canonical": canonical,
        "seo_image": f"{site_url}{static('posts/images/revue-favicon.png')}",
    }
