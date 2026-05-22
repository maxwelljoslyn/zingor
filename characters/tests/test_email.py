import pytest
from django.conf import settings
from django.core.mail import send_mail
from django.test import override_settings


@pytest.mark.skipif(
    "smtp" not in settings.EMAIL_BACKEND.lower(),
    reason="EMAIL_BACKEND is not SMTP; skipping live email test",
)
@override_settings(EMAIL_BACKEND=settings.EMAIL_BACKEND)
def test_smtp_connection_live():
    """Send a real email through the configured SMTP backend.
    pytest-django swaps in a locmem backend by default, so we override it back.
    Run explicitly with: uv run pytest characters/tests/test_email.py -k live
    """
    send_mail(
        subject="Zingor SMTP smoke test",
        message="If you received this, SMTP is working.",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=["maxwelljoslyn@gmail.com"],
    )
