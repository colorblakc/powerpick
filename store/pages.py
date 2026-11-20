"""Help pages (about, contact, policies), error pages and robots.txt.

Page content lives in templates/store/pages/<slug>.html. The title and summary
for each page are kept here so the header, the browser title and the tests agree.
"""
from django.conf import settings
from django.http import Http404, HttpResponse, HttpResponseServerError
from django.shortcuts import render
from django.template import TemplateDoesNotExist, loader

PAGES = {
    "about": {"title": "About Power Pick", "summary": "An online electrical supplies store for electricians and homeowners. This page explains how the catalogue is organised and how an order works."},
    "contact": {"title": "Contact", "summary": "How to reach the store, and what the on-site assistant can answer."},
    "delivery-and-payments": {"title": "Delivery and payments", "summary": "How delivery details are collected, how online payment through Razorpay works, and how orders move from Pending to Delivered."},
    "cancellations": {"title": "Cancellations", "summary": "When an order can be cancelled, who can cancel it, and what happens to the stock."},
    "privacy": {"title": "Privacy", "summary": "What Power Pick stores about you, what it sends to other services, and what it never stores."},
    "terms": {"title": "Terms of use", "summary": "Plain-language terms for using the Power Pick website and placing orders."},
}
SLUGS = set(PAGES)

ROBOTS = """User-agent: *
Allow: /
Disallow: /staff/
Disallow: /admin/
Disallow: /cart/
Disallow: /checkout/
Disallow: /payments/
Disallow: /account/
Disallow: /accounts/
Disallow: /orders/
Disallow: /payment-history/
Disallow: /assistant/
"""


def contact_details():
    """Optional store contact details from settings. Empty values are never invented."""
    details = {
        "name": getattr(settings, "STORE_CONTACT_NAME", "").strip(),
        "email": getattr(settings, "STORE_CONTACT_EMAIL", "").strip(),
        "phone": getattr(settings, "STORE_CONTACT_PHONE", "").strip(),
        "address": getattr(settings, "STORE_CONTACT_ADDRESS", "").strip(),
    }
    details["any"] = any(details.values())
    return details


def page(request, slug):
    """Show a known help or policy page, including the current store contact details."""
    if slug not in SLUGS:
        raise Http404
    context = {"slug": slug, "page": PAGES[slug]}
    if slug == "contact":
        context["contact"] = contact_details()
    try:
        return render(request, f"store/pages/{slug}.html", context)
    except TemplateDoesNotExist:
        raise Http404


def robots_txt(request):
    """Tell search engines which parts of the website they may visit."""
    return HttpResponse(ROBOTS, content_type="text/plain; charset=utf-8")


def not_found(request, exception=None):
    return render(request, "store/404.html", status=404)


def permission_denied(request, exception=None):
    return render(request, "store/403.html", status=403)


def server_error(request):
    # Render without the request so no context processor (and so no database query) can fail here.
    try:
        body = loader.get_template("store/500.html").render()
    except Exception:
        body = "<!doctype html><title>Something went wrong</title><h1>Something went wrong</h1><p>Please try again in a moment.</p>"
    return HttpResponseServerError(body)
