from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode


def send_confirmation_email(user, request):
    if not settings.EMAIL_CONFIRMATION_REQUIRED:
        user.profile.email_confirmed = True
        user.profile.save(update_fields=["email_confirmed"])
        return

    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    confirm_url = request.build_absolute_uri(
        reverse(
            "characters:register_confirm",
            kwargs={"uidb64": uid, "token": token},
        )
    )
    body = render_to_string(
        "registration/confirmation_email.txt",
        {"user": user, "confirm_url": confirm_url},
    )
    send_mail(
        subject="Confirm your Zingor account",
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )
