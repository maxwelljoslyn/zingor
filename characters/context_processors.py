from django.conf import settings


def registration_enabled(request):
    """Expose REGISTRATION_ENABLED to templates so the Register link can be hidden."""
    return {"registration_enabled": settings.REGISTRATION_ENABLED}
