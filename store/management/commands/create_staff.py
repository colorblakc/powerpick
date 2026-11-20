"""Create an administrator account for the staff workspace.

    python manage.py create_staff --username asha --email asha@example.com
    python manage.py create_staff --username ravi --promote     (turn an existing account into staff)

The password is typed at a hidden prompt, never on the command line, and must pass Django's password rules.
"""
import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email


class Command(BaseCommand):
    help = ("Create a staff (administrator) account. Prompts for the password and applies Django's password "
            "rules. Sets is_staff only, never superuser. Refuses to touch an existing user unless --promote is given.")

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True, help="Sign-in name for the new staff account.")
        parser.add_argument("--email", default="", help="Email address. Required for a new account.")
        parser.add_argument("--promote", action="store_true",
                            help="Make an existing account staff. Its password and other details are left unchanged.")

    def handle(self, *args, **options):
        User = get_user_model()
        username, email = options["username"].strip(), options["email"].strip()
        existing = User.objects.filter(username__iexact=username).first()

        if existing:
            if not options["promote"]:
                raise CommandError(f"The user '{existing.username}' already exists. Nothing was changed. "
                                   "Use --promote to give that account staff access.")
            existing.is_staff = True
            existing.save(update_fields=["is_staff"])
            self.stdout.write(self.style.SUCCESS(f"'{existing.username}' now has staff access."))
            return

        if options["promote"]:
            raise CommandError(f"There is no user '{username}' to promote. Leave out --promote to create the account.")
        if not email:
            raise CommandError("Give an email address with --email for a new account.")
        try:
            validate_email(email)
        except ValidationError:
            raise CommandError(f"'{email}' is not a valid email address.")

        user = User(username=username, email=email, is_staff=True)
        try:
            user.full_clean(exclude=["password"])
        except ValidationError as error:
            raise CommandError("; ".join(message for messages in error.message_dict.values() for message in messages))

        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Password (again): "):
            raise CommandError("The two passwords did not match. No account was created.")
        try:
            validate_password(password, user)
        except ValidationError as error:
            raise CommandError("That password is not allowed: " + " ".join(error.messages))

        user.set_password(password)
        user.save()
        self.stdout.write(self.style.SUCCESS(f"Created staff account '{user.username}'. They can sign in at /accounts/login/."))
