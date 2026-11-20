"""Sign in, registration, the customer account area, order history, tracking and receipts."""
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, F
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_POST

from .forms import (AccountForm, LoginForm, ProfileDeliveryForm, RegisterForm,
                    StyledPasswordChangeForm)
from .models import AVATAR_CHOICES, Order, Product, Profile

# The order of a normal delivery, then the cancelled branch.
FLOW = ["Pending", "Confirmed", "Processing", "Shipped", "Delivered"]
ORDER_STATUSES = FLOW + ["Cancelled"]
PAYMENT_STATUSES = ["Paid", "Unpaid", "Failed"]
STATUS_TONE = {"Pending": "warn", "Confirmed": "blue", "Processing": "blue", "Shipped": "blue",
               "Delivered": "ok", "Cancelled": "fault", "Payment review": "warn"}
PAYMENT_TONE = {"Paid": "ok", "Unpaid": "warn", "Failed": "fault"}
PAGE_SIZE = 10


def display_name(user):
    """Short name for greetings: first name when there is one, else the username."""
    return user.first_name or user.username


def first_name_greeting(user):
    """Name printed on a receipt: full name when set, else the username."""
    return user.get_full_name().strip() or user.username


# ---- Sign in and registration ----

class StoreLoginView(LoginView):
    """One sign-in page for customers and staff. Staff land in the workspace, customers where they were going."""
    form_class = LoginForm
    template_name = "registration/login.html"
    redirect_authenticated_user = True

    def get_success_url(self):
        # get_redirect_url refuses addresses on other sites.
        target = self.get_redirect_url()
        user = self.request.user
        if user.is_staff:
            staff_home = reverse("dashboard")
            return target if target.startswith(staff_home) else staff_home
        return target or reverse("home")

    def form_valid(self, form):
        response = super().form_valid(form)
        user = form.get_user()
        if user.is_staff:
            messages.success(self.request, f"Welcome back, {display_name(user)}. You are in the staff workspace.")
        else:
            messages.success(self.request, f"Welcome back, {display_name(user)}.")
        return response


def register(request):
    """Create a customer account and sign them in with their new credentials."""
    if request.user.is_authenticated:
        return redirect("profile")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            user = form.save()
        login(request, user, backend="store.backends.EmailOrUsernameBackend")
        messages.success(request, f"Welcome to Power Pick, {display_name(user)}. Add your delivery details so checkout is quicker.")
        return redirect(reverse("profile") + "#delivery")
    return render(request, "registration/register.html", {"form": form})


class StorePasswordChangeView(PasswordChangeView):
    form_class = StyledPasswordChangeForm
    template_name = "registration/password_change.html"
    success_url = reverse_lazy("password_change_done")


@login_required
def password_change_done(request):
    return render(request, "registration/password_change_done.html")


# ---- Profile ----

@login_required
def profile(request):
    """Show and update the signed-in person's account and delivery details."""
    saved, _ = Profile.objects.get_or_create(user=request.user)
    section = request.POST.get("section", "")
    posted = request.method == "POST"
    # Each section saves on its own. A post that names no section saves both forms together.
    person = AccountForm(request.POST if posted and section in ("", "person") else None, instance=request.user)
    # The address is only checked when the Delivery section is saved (or a sectionless post carries one).
    wants_delivery = section == "delivery" or (section == "" and "line1" in request.POST)
    delivery = ProfileDeliveryForm(request.POST if posted and wants_delivery else None, instance=saved)
    if posted:
        checks = [form for form in (person, delivery) if form.is_bound]
        if all(form.is_valid() for form in checks):
            with transaction.atomic():
                for form in checks:
                    form.save()
            messages.success(request, "Delivery details saved. Checkout will use them." if section == "delivery"
                             else "Personal details saved." if section == "person" else "Your details have been saved.")
            return redirect(reverse("profile") + {"person": "#details", "delivery": "#delivery"}.get(section, ""))
    recent = list(Order.objects.filter(user=request.user).select_related("payment")
                  .prefetch_related("items__product").order_by("-pk")[:3])
    decorate(recent)
    return render(request, "store/profile.html", {
        "person": person, "delivery": delivery, "saved": saved, "recent": recent,
        "avatar_choices": [{"value": value, "label": label, "path": f"store/avatars/{value}.webp"} for value, label in AVATAR_CHOICES],
        "order_count": Order.objects.filter(user=request.user).count(),
        "wishlist_count": request.user.wishlist.count(),
        "member_since": request.user.date_joined,
    })


@login_required
@require_POST
def update_avatar(request):
    """Save a store-provided picture for the signed-in person's account only."""
    choice = request.POST.get("avatar", "")
    if choice not in dict(AVATAR_CHOICES):
        messages.error(request, "Choose one of the available profile pictures.")
    else:
        Profile.objects.update_or_create(user=request.user, defaults={"avatar": choice})
        messages.success(request, "Profile picture updated.")
    return redirect(reverse("profile") + "#avatar")


# ---- Orders and payment history ----

def decorate(orders):
    """Attach display tones so templates stay free of logic."""
    for order in orders:
        order.status_tone = STATUS_TONE.get(order.status, "")
        payment = getattr(order, "payment", None)
        order.pay_tone = PAYMENT_TONE.get(payment.status, "") if payment else ""
        items = list(order.items.all())
        order.item_list = items
        order.item_preview = items[:3]
        order.item_more = max(len(items) - 3, 0)
    return orders


@login_required
def orders(request, payments=False):
    """Show only the signed-in person's orders or payment records."""
    mine = Order.objects.filter(user=request.user)
    field = "payment__status" if payments else "status"
    allowed = PAYMENT_STATUSES if payments else ORDER_STATUSES
    counts = {row[field]: row["n"] for row in mine.values(field).annotate(n=Count("pk"))}
    status = request.GET.get("status", "")
    status = status if status in allowed else ""
    records = mine.select_related("payment").prefetch_related("items__product").order_by("-pk")
    if status:
        records = records.filter(**{field: status})
    page = Paginator(records, PAGE_SIZE).get_page(request.GET.get("page"))
    decorate(page.object_list)
    chips = [{"label": "All", "value": "", "count": mine.count(), "active": not status}]
    chips += [{"label": name, "value": name, "count": counts.get(name, 0), "active": status == name} for name in allowed]
    return render(request, "store/orders.html", {"page": page, "records": page.object_list, "payments": payments,
                                                  "chips": chips, "status": status, "total_orders": chips[0]["count"]})


def tracking(order):
    """Six statuses along one line: five steps in order and a Cancelled branch."""
    status = order.status
    branch = status in ("Cancelled", "Payment review")
    index = FLOW.index(status) if status in FLOW else 0
    steps = []
    for number, name in enumerate(FLOW):
        if branch:
            state = "done" if number == 0 else "todo"
        else:
            state = "done" if number < index else "current" if number == index else "todo"
        steps.append({"name": name, "state": state})
    steps[0]["when"] = order.created
    return {"steps": steps, "branch": branch,
            "branch_label": "Payment review" if status == "Payment review" else "Cancelled",
            "branch_state": "current" if branch else "todo", "branch_tone": "warn" if status == "Payment review" else "fault"}


def owned_order(request, pk):
    """Fetch an order that belongs to the signed-in customer; anyone else's order is a 404."""
    return get_object_or_404(Order.objects.select_related("payment", "user").prefetch_related("items__product"),
                             user=request.user, pk=pk)


def can_cancel_cod(order):
    """A cash on delivery order can be cancelled by its owner until staff start preparing it."""
    payment = order.payment
    return payment.method == "COD" and payment.status != "Paid" and order.status in ("Pending", "Confirmed")


@login_required
@require_POST
def cancel_cod(request, pk):
    """Cancel an own cash on delivery order and return its items to stock exactly once."""
    order = owned_order(request, pk)
    if order.payment.method != "COD":
        messages.error(request, "This order is paid online. Cancel it from its payment page.")
        return redirect("order_detail", pk=pk)
    with transaction.atomic():
        # The status check in the UPDATE lets only one of two quick clicks release stock.
        changed = Order.objects.filter(pk=pk, status__in=("Pending", "Confirmed"), payment__method="COD",
                                       payment__status="Unpaid").update(status="Cancelled")
        if changed:
            for item in order.items.all():
                Product.objects.filter(pk=item.product_id).update(stock=F("stock") + item.quantity)
    if changed:
        messages.success(request, f"Order #{pk} is cancelled. The reserved items went back to stock.")
    else:
        messages.error(request, "This order can no longer be cancelled here. Staff may already be preparing it; see Contact for help.")
    return redirect("order_detail", pk=pk)


@login_required
def order_detail(request, pk):
    order = owned_order(request, pk)
    decorate([order])
    payment = order.payment
    payable = payment.method == "Razorpay" and payment.status != "Paid" and order.status == "Pending"
    lines = [(item, item.price * item.quantity) for item in order.item_list]
    return render(request, "store/order.html", {
        "order": order, "payment": payment, "track": tracking(order), "payable": payable,
        "retry": payable and payment.status == "Failed", "lines": lines,
        "cod": payment.method == "COD", "can_cancel_cod": can_cancel_cod(order),
        "placed": payment.method == "COD" and request.GET.get("placed") == "1" and order.status == "Confirmed",
        "can_reorder": any(item.product_id for item in order.item_list)})


@login_required
def receipt(request, pk):
    records = Order.objects.select_related("payment", "user").prefetch_related("items")
    if not request.user.is_staff:
        records = records.filter(user=request.user)
    order = get_object_or_404(records, pk=pk)
    decorate([order])
    return render(request, "store/receipt.html", {
        "order": order, "payment": order.payment, "customer": first_name_greeting(order.user),
        "lines": [(item, item.price * item.quantity) for item in order.item_list]})


@login_required
@require_POST
def reorder(request, pk):
    """Add what is still on sale, within stock, to the cart and say what could not be added."""
    order = owned_order(request, pk)
    basket = dict(request.session.get("cart", {}))
    added, skipped = 0, []
    for item in order.items.all():
        product = item.product
        if product is None or not product.available:
            skipped.append(f"{item.name} (no longer sold)")
            continue
        key = str(product.pk)
        in_cart = int(basket.get(key, 0))
        room = min(product.stock, 999) - in_cart
        if room <= 0:
            skipped.append(f"{item.name} (out of stock)" if not product.stock else f"{item.name} (all {product.stock} in stock are already in your cart)")
            continue
        qty = min(item.quantity, room)
        basket[key] = in_cart + qty
        added += qty
        if qty < item.quantity:
            skipped.append(f"{item.name} (only {qty} of {item.quantity} added, stock limit)")
    if added:
        request.session["cart"] = basket
        request.session.pop("checkout_token", None)
        messages.success(request, f"Added {added} item{'s' if added != 1 else ''} from order {order.pk} to your cart. Prices are today's prices.")
    if skipped:
        messages.warning(request, "Could not add: " + "; ".join(skipped) + ".")
    return redirect("cart" if added else "order_detail", **({} if added else {"pk": order.pk}))
