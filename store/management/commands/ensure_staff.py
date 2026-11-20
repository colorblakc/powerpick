"""Create the first staff account from environment variables, if it does not exist yet.

Meant for container start-up, where nobody is at a keyboard to answer a password prompt:

    STAFF_USERNAME=admin STAFF_EMAIL=you@example.com STAFF_PASSWORD=... python manage.py ensure_staff

It does nothing when the variables are missing or the account already exists, so it is safe on every start.
"""
import os

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create a staff account from STAFF_USERNAME, STAFF_EMAIL and STAFF_PASSWORD when it is missing."

    def handle(self, *args, **options):
        username = os.getenv("STAFF_USERNAME", "").strip()
        email = os.getenv("STAFF_EMAIL", "").strip()
        password = os.getenv("STAFF_PASSWORD", "")
        if not (username and email and password):
            self.stdout.write("STAFF_USERNAME, STAFF_EMAIL and STAFF_PASSWORD are not all set; no staff account created.")
            return
        User = get_user_model()
        if User.objects.filter(username__iexact=username).exists():
            self.stdout.write(f"Staff account '{username}' already exists; left unchanged.")
            return
        user = User(username=username, email=email, is_staff=True)
        try:
            validate_password(password, user)
        except ValidationError as error:
            self.stderr.write("STAFF_PASSWORD is not allowed: " + " ".join(error.messages))
            return
        user.set_password(password)
        user.save()
        self.stdout.write(self.style.SUCCESS(f"Created staff account '{username}'."))
