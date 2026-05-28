import os

from django.conf import settings
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
    }
