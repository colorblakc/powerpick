"""Let people sign in with their email address as well as their username."""
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User


class EmailOrUsernameBackend(ModelBackend):
    """Translate an email to a username, then let Django verify the password normally."""
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username and "@" in username:
            user = User.objects.filter(email__iexact=username).order_by("pk").first()
            username = user.username if user else username
        return super().authenticate(request, username=username, password=password, **kwargs)
