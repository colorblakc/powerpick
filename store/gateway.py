"""Razorpay test checkout. The browser opens Checkout; Django decides what was paid."""
import base64
import hashlib
import hmac
import json
import os
import re
import socket
import ssl
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import F
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt

from .models import Order, Payment, Product


# A claim to create the provider order is honoured for this many seconds before another request may take over.
CREATE_WINDOW = 60


class GatewayError(Exception):
    """A message we can show without exposing passwords or the provider's response.

    code lets the page pick a state: "config" (keys missing or refused), "review" (details differ,
    staff must look), "network" (try again) or "" (a plain refusal). definite is True only when the
    provider certainly did not act on the request, so the caller may safely release its claim.
    """

    def __init__(self, message, code="", definite=False):
        super().__init__(message)
        self.code = code
        self.definite = definite


def credentials():
    """Read payment keys on the server and allow only the configured test account."""
    key = os.getenv("RAZORPAY_KEY_ID", "")
    secret = os.getenv("RAZORPAY_KEY_SECRET", "")
    if not key.startswith("rzp_test_") or not secret:
        raise GatewayError("Online payment is temporarily unavailable. Please try again later.", code="config")
    return key, secret


def api(path, payload=None):
    """Call Razorpay privately and turn connection failures into safe customer messages."""
    key, secret = credentials()
    auth = base64.b64encode(f"{key}:{secret}".encode()).decode()
    request = Request("https://api.razorpay.com/v1/" + path,
                      headers={"Authorization": "Basic " + auth, "Content-Type": "application/json"},
                      data=json.dumps(payload).encode() if payload is not None else None)
    try:
        with urlopen(request, timeout=10) as response:
            result = json.load(response)
        if not isinstance(result, dict):
            raise ValueError("Unexpected response")
        return result
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise GatewayError("Razorpay did not accept the payment keys. Ask store staff to check the payment setup.",
                               code="config", definite=True) from exc
        # A 4xx answer means Razorpay refused the request. A 5xx answer leaves it uncertain.
        raise GatewayError("We could not reach or confirm with Razorpay. Your order is saved. Try again.",
                           code="network", definite=exc.code < 500) from exc
    except (URLError, OSError, ValueError) as exc:
        # Only a failure to connect proves nothing arrived. A timeout may hide a request that succeeded.
        reason = getattr(exc, "reason", exc)
        never_sent = isinstance(reason, (ConnectionRefusedError, socket.gaierror, ssl.SSLError))
        raise GatewayError("We could not reach or confirm with Razorpay. Your order is saved. Try again.",
                           code="network", definite=never_sent) from exc


def owned_payment(request, pk, allow_staff=False):
    """Find this order’s payment only for its owner, or a staff member when allowed."""
    records = Payment.objects.select_related("order").filter(method="Razorpay")
    if not (allow_staff and request.user.is_staff):
        records = records.filter(order__user=request.user)
    return get_object_or_404(records, order_id=pk)


def amount(payment):
    # Razorpay uses whole paise, so ₹12.50 is sent as 1250.
    return int(payment.order.total * 100)


def remember_capture(payment, record):
    # Reading the provider's own record protects against a forged browser success message.
    if (record.get("order_id") != payment.gateway_order or record.get("currency") != "INR"
            or record.get("amount") != amount(payment) or record.get("status") != "captured"
            or not re.fullmatch(r"pay_[A-Za-z0-9]+", str(record.get("id", "")))):
        return False
    with transaction.atomic():
        # Only the first successful check can change this order. Refresh and retry are safe.
        changed = Payment.objects.filter(pk=payment.pk, gateway_order=payment.gateway_order,
                                         ).exclude(status="Paid").update(
                                             status="Paid", reference=record["id"])
        if changed:
            # A payment that arrives after cancellation must remain visible to staff.
            # Stock has already been released, so this order needs manual resolution.
            Order.objects.filter(pk=payment.order_id, status="Cancelled").update(status="Payment review")
            Order.objects.filter(pk=payment.order_id, status="Pending").update(status="Confirmed")
    payment.refresh_from_db()
    return payment.status == "Paid" and payment.reference == record["id"]


def reconcile(payment):
    """Ask Razorpay for the latest payment attempts before allowing another action."""
    # If the browser closed after paying, the gateway still knows the result.
    if payment.status == "Paid":
        return True
    if not payment.gateway_order.startswith("order_"):
        return False
    records = api(f"orders/{payment.gateway_order}/payments").get("items")
    if not isinstance(records, list):
        raise GatewayError("Razorpay could not confirm payment. Please check again.", code="pending")
    for record in records:
        if record.get("status") == "captured":
            if remember_capture(payment, record):
                return True
            # A captured transaction with conflicting details needs review before another attempt.
            raise GatewayError("The gateway details differ from this order. Ask store staff to review it.", code="review")
    if any(r.get("status") == "authorized" for r in records):
        raise GatewayError("Razorpay is confirming the payment. Check its status before paying again.", code="pending")
    if records and all(r.get("status") == "failed" for r in records):
        Payment.objects.filter(pk=payment.pk).exclude(status="Paid").update(status="Failed")
    return False


def _creating(value):
    """True while a request has claimed the right to create the Razorpay order (value is "creating" or "creating:<time>")."""
    return value == "creating" or value.startswith("creating:")


def _claim_is_stale(value):
    # "creating" without a time was written by an older version, so no request can still hold it.
    stamp = value.partition(":")[2]
    return not stamp.isdigit() or time.time() - int(stamp) > CREATE_WINDOW


def _checked_remote_order(payment, record, receipt):
    order_id = str(record.get("id", ""))
    if (record.get("amount") != amount(payment) or record.get("currency") != "INR"
            or record.get("receipt") != receipt or not re.fullmatch(r"order_[A-Za-z0-9]+", order_id)):
        raise GatewayError("Razorpay returned different order details. Checkout has been paused.", code="review")
    return order_id


def _find_remote_order(receipt):
    records = api(f"orders?receipt={receipt}").get("items", [])
    return next((r for r in records if isinstance(r, dict) and r.get("receipt") == receipt), None)


def gateway_order(payment):
    """Reuse or recover the gateway order so repeated clicks do not create new payments."""
    # Reuse one provider order for every retry. The receipt also recovers an order
    # created remotely just before a lost network response.
    receipt = payment.order.token.hex
    if payment.gateway_order.startswith("order_"):
        return payment.gateway_order
    marker = f"creating:{int(time.time())}"
    fresh = Payment.objects.filter(pk=payment.pk, gateway_order="", order__status="Pending").update(
        gateway_order=marker)
    payment.refresh_from_db()
    if payment.gateway_order.startswith("order_"):
        return payment.gateway_order
    if not _creating(payment.gateway_order):
        raise GatewayError("This order is no longer awaiting checkout.", code="closed")
    held = payment.gateway_order
    existing = None if fresh else _find_remote_order(receipt)
    if not fresh and not existing:
        # Another request may still be reaching Razorpay or awaiting indexing. Creating again here
        # could create two gateway orders for one basket, so wait unless that claim has gone stale
        # (its request failed or the server stopped). The conditional update lets one request take over.
        if not _claim_is_stale(held) or not Payment.objects.filter(
                pk=payment.pk, gateway_order=held).update(gateway_order=marker):
            raise GatewayError("The payment order is still being checked. Please try again shortly.", code="pending")
        held = marker
    try:
        record = existing or api("orders", {"amount": amount(payment), "currency": "INR", "receipt": receipt, "payment_capture": 1})
    except GatewayError as exc:
        if exc.definite:
            # Nothing was created, so release the claim and let the next attempt start cleanly.
            Payment.objects.filter(pk=payment.pk, gateway_order=held).update(gateway_order="")
        raise
    order_id = _checked_remote_order(payment, record, receipt)
    Payment.objects.filter(pk=payment.pk, gateway_order=held).update(gateway_order=order_id)
    payment.refresh_from_db()
    if not payment.gateway_order.startswith("order_"):
        raise GatewayError("The payment order is still being checked. Please try again shortly.", code="pending")
    return payment.gateway_order


def adopt_remote_order(payment):
    """Cancelling never creates a provider order: it only recovers one that a lost response left behind."""
    if not _creating(payment.gateway_order):
        return
    receipt = payment.order.token.hex
    record = _find_remote_order(receipt)
    if record:
        order_id = _checked_remote_order(payment, record, receipt)
        Payment.objects.filter(pk=payment.pk, gateway_order=payment.gateway_order).update(gateway_order=order_id)
    elif _claim_is_stale(payment.gateway_order):
        Payment.objects.filter(pk=payment.pk, gateway_order=payment.gateway_order).update(gateway_order="")
    else:
        raise GatewayError("The payment order is still being checked. Please try again shortly.", code="pending")
    payment.refresh_from_db()


def result(payment):
    """The JSON the payment page receives once an order is paid."""
    try:
        receipt_url = reverse("receipt", args=[payment.order_id])
    except NoReverseMatch:
        receipt_url = ""
    return {"paid": True, "order": payment.order_id, "reference": payment.reference,
            "order_url": reverse("order_detail", args=[payment.order_id]), "receipt_url": receipt_url}


def prefill(payment):
    """Details Razorpay Checkout may pre-fill. Only values this customer already gave us are sent."""
    user = payment.order.user
    data = {}
    if user.get_full_name().strip():
        data["name"] = user.get_full_name().strip()
    if user.email:
        data["email"] = user.email
    contact = re.sub(r"[^0-9+]", "", payment.order.phone)
    if re.fullmatch(r"[6-9][0-9]{9}", contact):
        contact = "+91" + contact  # Razorpay pre-fills Indian mobile numbers written with the country code
    if re.fullmatch(r"\+?[0-9]{10,15}", contact):
        data["contact"] = contact
    return data


def error_response(exc):
    """Send a gateway problem to the page as a 409 with its state code."""
    return JsonResponse({"error": str(exc), "code": exc.code}, status=409)


@login_required
@require_GET
def page(request, pk):
    """The payment screen for one order, in whichever state the saved order and payment are in."""
    payment = owned_payment(request, pk)
    order = payment.order
    try:
        credentials()
        configured = True
    except GatewayError:
        configured = False
    # The saved status decides what a refreshed or reopened page offers.
    if order.status == "Payment review":
        state = "review"
    elif payment.status == "Paid":
        state = "success"
    elif order.status == "Pending":
        state = "ready" if configured else "config"
    else:
        state = "closed"
    return render(request, "store/gateway.html", {
        "payment": payment, "order": order, "items": order.items.all(), "state": state,
        "can_pay": state == "ready", "retrying": payment.status == "Failed"})


@login_required
@require_POST
def start(request, pk):
    """Give the browser everything it needs to open Razorpay Checkout, or report that the order is already paid."""
    payment = owned_payment(request, pk)
    try:
        if payment.status == "Paid":
            return JsonResponse(result(payment))
        if payment.order.status != "Pending":
            raise GatewayError("This order is no longer awaiting payment.", code="closed")
        key, _ = credentials()
        identifier = gateway_order(payment)
        if reconcile(payment):
            return JsonResponse(result(payment))
        return JsonResponse({"key": key, "order_id": identifier, "amount": amount(payment),
                             "currency": "INR", "name": "Power Pick",
                             "description": f"Order {payment.order_id}", "prefill": prefill(payment)})
    except GatewayError as exc:
        return error_response(exc)


@login_required
@require_POST
def verify(request, pk):
    """Check the returned signature and fetch the actual payment before confirming an order."""
    payment = owned_payment(request, pk)
    try:
        _, secret = credentials()
        order_id = request.POST.get("razorpay_order_id", "")
        pay_id = request.POST.get("razorpay_payment_id", "")
        signature = request.POST.get("razorpay_signature", "")
        if (order_id != payment.gateway_order or not re.fullmatch(r"order_[A-Za-z0-9]+", order_id)
                or not re.fullmatch(r"pay_[A-Za-z0-9]{1,80}", pay_id)
                or not re.fullmatch(r"[0-9a-f]{64}", signature)):
            raise GatewayError("The checkout details could not be verified. Check the payment status before trying again.", code="pending")
        # Razorpay signs "<order id>|<payment id>" with our secret, so a match proves the payment belongs to this order.
        expected = hmac.new(secret.encode(), f"{payment.gateway_order}|{pay_id}".encode(),
                            hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise GatewayError("The payment signature could not be verified. Check the payment status before trying again.", code="pending")
        if payment.status != "Paid" or payment.reference != pay_id:
            record = api("payments/" + pay_id)
            if record.get("id") != pay_id or not remember_capture(payment, record):
                raise GatewayError("Payment has not been confirmed. Check the status before trying again.", code="pending")
        return JsonResponse(result(payment))
    except GatewayError as exc:
        return error_response(exc)


@login_required
@require_POST
def check(request, pk):
    """Refresh an owned payment’s status when a customer or staff member asks."""
    payment = owned_payment(request, pk, allow_staff=True)
    staff_page = request.user.is_staff and request.POST.get("return_to") == "staff"
    try:
        paid = reconcile(payment)
        payment.refresh_from_db()
        if staff_page:
            messages.info(request, f"Verified payment status: {payment.status}.")
            return redirect("sale", pk=pk)
        return JsonResponse(result(payment) if paid else {"paid": False, "status": payment.status})
    except GatewayError as exc:
        if staff_page:
            messages.error(request, str(exc))
            return redirect("sale", pk=pk)
        return error_response(exc)


@login_required
@require_POST
def cancel(request, pk):
    """Release an unpaid order's stock once, after checking for a gateway payment."""
    payment = owned_payment(request, pk, allow_staff=True)
    destination = "sale" if request.user.is_staff and request.POST.get("return_to") == "staff" else "order_detail"
    try:
        # Recover a remote order first. Its creation may have outlived a timeout.
        adopt_remote_order(payment)
        if reconcile(payment):
            raise GatewayError("Payment has been received. This order cannot be cancelled here.")
        with transaction.atomic():
            # This conditional update arbitrates with a simultaneous capture callback.
            changed = Order.objects.filter(pk=pk, status="Pending").exclude(payment__status="Paid").update(status="Cancelled")
            if changed:
                for item in payment.order.items.all():
                    Product.objects.filter(pk=item.product_id).update(stock=F("stock") + item.quantity)
                messages.success(request, "Order cancelled. Reserved items have been returned to stock.")
            else:
                messages.info(request, "This order is no longer awaiting cancellation.")
    except GatewayError as exc:
        messages.error(request, str(exc))
    return redirect(destination, pk=pk)


@csrf_exempt
@require_POST
def webhook(request):
    """Razorpay can confirm capture even when the customer closes their browser."""
    secret = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")
    if not secret:
        return JsonResponse({"error": "Webhook is not configured."}, status=503)
    if len(request.body) > 65536:
        return JsonResponse({"error": "Payload too large."}, status=413)
    # This endpoint is called by Razorpay, so its signature replaces the browser CSRF token.
    signature = request.headers.get("X-Razorpay-Signature", "")
    expected = hmac.new(secret.encode(), request.body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return JsonResponse({"error": "Invalid signature."}, status=400)
    try:
        event = json.loads(request.body)
        if event.get("event") not in {"payment.captured", "order.paid"}:
            return JsonResponse({"received": True})
        record = event["payload"]["payment"]["entity"]
        payment = Payment.objects.select_related("order").filter(method="Razorpay", gateway_order=record["order_id"]).first()
        if payment is None:
            # Creation may still be recovering from a timeout. Ask Razorpay to retry.
            return JsonResponse({"error": "Order is not ready."}, status=503)
        payment_id = str(record["id"])
        if not re.fullmatch(r"pay_[A-Za-z0-9]{1,80}", payment_id):
            raise ValueError
        confirmed = api("payments/" + payment_id)
        if confirmed.get("id") != payment_id or not remember_capture(payment, confirmed):
            return JsonResponse({"error": "Payment could not be confirmed."}, status=409)
    except (ValueError, KeyError, TypeError):
        return JsonResponse({"error": "Invalid event."}, status=400)
    except GatewayError:
        return JsonResponse({"error": "Verification unavailable. Retry later."}, status=503)
    return JsonResponse({"received": True})
