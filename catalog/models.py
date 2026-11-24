from django.conf import settings


def actor_name(user):
    return (getattr(user, "email", None) or user.get_username() or "")[:80]


def is_cataloger(user):
    return user.is_authenticated and user.groups.filter(name=settings.CATALOGUER_GROUP).exists()


def can_use_app(user):
    return is_cataloger(user)


def can_use_op(user, op):
    return can_use_app(user)
