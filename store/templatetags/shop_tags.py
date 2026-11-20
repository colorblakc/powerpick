"""Register the phone display filter used by the store’s HTML templates."""
from django import template

from ..address import pretty_phone

register = template.Library()
register.filter("phone", pretty_phone)
