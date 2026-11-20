"""Endpoints for opening the payment window and checking its outcome."""
from django.urls import path

from . import gateway

urlpatterns = [
    path("webhook/", gateway.webhook, name="gateway_webhook"),
    path("<int:pk>/cancel/", gateway.cancel, name="gateway_cancel"),
    path("<int:pk>/", gateway.page, name="gateway_page"),
    path("<int:pk>/start/", gateway.start, name="gateway_start"),
    path("<int:pk>/verify/", gateway.verify, name="gateway_verify"),
    path("<int:pk>/check/", gateway.check, name="gateway_reconcile"),
]
