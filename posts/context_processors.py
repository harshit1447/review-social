import os


def auth_options(request):
    return {
        "google_auth_enabled": bool(
            os.environ.get("GOOGLE_CLIENT_ID")
            and os.environ.get("GOOGLE_CLIENT_SECRET")
        )
    }
