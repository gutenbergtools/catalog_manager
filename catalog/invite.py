from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sites.shortcuts import get_current_site
from django.core import mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.http import urlsafe_base64_encode


def _context(request, user):
    site = get_current_site(request)
    return {
        "email": user.email,
        "site_name": site.name,
        "domain": site.domain,
        "protocol": "https" if request.is_secure() else "http",
        "uid": urlsafe_base64_encode(str(user.pk).encode()),
        "token": default_token_generator.make_token(user),
        "hours": max(1, round(settings.PASSWORD_RESET_TIMEOUT / 3600)),
    }


def reset_link(request, user):
    """A one-time link the user can use to choose their own password."""
    ctx = _context(request, user)
    return request.build_absolute_uri(
        reverse("password_reset_confirm", kwargs={"uidb64": ctx["uid"], "token": ctx["token"]})
    )


def send_invite(request, user):
    """Email the user a link to set their password. True when the mail went out.

    Passwords are never sent or even chosen here: the user picks their own
    behind the link, so nothing travels in plain text.
    """
    if not user.email:
        return False
    body = render_to_string("registration/password_reset_email.html", _context(request, user))
    return bool(
        mail.send_mail(
            "Catalog Manager password reset",
            body,
            None,  # DEFAULT_FROM_EMAIL
            [user.email],
            fail_silently=True,
        )
    )
