"""The staff workspace: one place for catalogue, stock, orders, payments, customers and assistant answers.

Every view here goes through `staff_required`. An online payment is marked paid only from Razorpay's
own record. The one hand-set payment status is `cash_collected`: staff record cash taken on delivery
for a Cash on delivery order that is Delivered.
"""
import csv
from datetime import timedelta
from decimal import Decimal
from functools import wraps

from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.views import PasswordChangeView, redirect_to_login
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import TruncDate
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_GET, require_POST

from .forms import (AddStockForm, CategoryForm, FAQForm, StaffCustomerForm, StaffDeliveryForm, StaffPasswordForm,
                    StaffProductForm, StaffProfileForm, StockForm)
from .models import Category, FAQ, Order, OrderItem, Payment, Product, Profile

LOW_STOCK = 5          # at or below this many units a product counts as low
PAGE_SIZE = 25
STATUSES = ["Pending", "Confirmed", "Processing", "Shipped", "Delivered", "Cancelled", "Payment review"]
FLOW = ["Pending", "Confirmed", "Processing", "Shipped", "Delivered"]
NEXT = {"Confirmed": "Processing", "Processing": "Shipped", "Shipped": "Delivered"}
TO_FULFIL = ["Confirmed", "Processing"]
PAYMENT_STATUSES = ["Paid", "Unpaid", "Failed"]


# ---- Shared helpers ----------------------------------------------------------

def staff_required(view):
    """Anonymous visitors go to sign-in; signed-in customers are sent back to the shop."""
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return redirect_to_login(request.get_full_path(), reverse("login"))
        if not (user.is_active and user.is_staff):
            messages.error(request, "That page is for store staff. Sign in with a staff account to open it.")
            return redirect("home")
        return view(request, *args, **kwargs)
    return wrapped


def attention_counts():
    """Small counts the rail shows beside Orders and Inventory."""
    return {
        "orders": Order.objects.filter(Q(status__in=TO_FULFIL) | Q(status="Payment review")).count(),
        "low": Product.objects.filter(available=True, stock__lte=LOW_STOCK).count(),
    }


def render_staff(request, template, section, **context):
    """Add the selected menu section and shared attention counts to a staff page."""
    context.update(section=section, attention=attention_counts())
    return render(request, template, context)


def wants_json(request):
    """Tell whether the browser requested a small in-place update rather than a full page."""
    return request.headers.get("X-Requested-With") == "fetch"


def safe_next(request, fallback):
    """Return to the page the form came from, but only if it is on this site."""
    target = request.POST.get("next", "")
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return target
    return fallback


def paginate(request, queryset, size=PAGE_SIZE):
    """Split a long list into pages and handle a missing or invalid page number."""
    return Paginator(queryset, size).get_page(request.GET.get("page"))


def query_without(request, *drop):
    """Keep the current search filters while removing fields such as the old page number."""
    params = request.GET.copy()
    for key in drop:
        params.pop(key, None)
    return params.urlencode()


def with_param(request, key, value):
    """Current filters with one changed, for filter chips. Paging restarts."""
    params = request.GET.copy()
    params.pop("page", None)
    if value:
        params[key] = value
    else:
        params.pop(key, None)
    encoded = params.urlencode()
    return "?" + encoded if encoded else "?"


def date_range(request):
    """Read the optional date filters from the page address."""
    start, end = parse_date(request.GET.get("from", "") or ""), parse_date(request.GET.get("to", "") or "")
    return start, end


def money(value):
    """An aggregate over no rows is None; show it as zero rupees."""
    return value or Decimal("0.00")


def first_error(form):
    """Return a short message that can fit beside an inline edit."""
    for errors in form.errors.values():
        return errors[0]
    return "Check the value and try again."


# ---- Overview ---------------------------------------------------------------

@staff_required
def dashboard(request):
    """Summarize paid orders, work awaiting staff, low stock and recent activity."""
    today = timezone.localdate()
    paid_orders = Order.objects.filter(payment__status="Paid")
    revenue = []
    for label, days in (("Today", 0), ("Last 7 days", 6), ("Last 30 days", 29)):
        total = paid_orders.filter(created__date__gte=today - timedelta(days=days)).aggregate(
            total=Sum("total"), count=Count("pk"))
        revenue.append({"label": label, "total": money(total["total"]), "count": total["count"]})

    by_status = dict(Order.objects.values_list("status").annotate(n=Count("pk")))
    status_rows = [{"status": s, "count": by_status.get(s, 0)} for s in STATUSES]
    to_fulfil = sum(by_status.get(s, 0) for s in TO_FULFIL)
    review = by_status.get("Payment review", 0)
    awaiting = Payment.objects.filter(status__in=["Unpaid", "Failed"], order__status="Pending").count()
    low_products = Product.objects.filter(available=True, stock__lte=LOW_STOCK)
    low_count = low_products.count()
    needs = [
        {"count": to_fulfil, "label": "orders to pack or ship", "url": reverse("sales") + "?status=to_fulfil",
         "detail": f"{by_status.get('Confirmed', 0)} confirmed, {by_status.get('Processing', 0)} processing"},
        {"count": awaiting, "label": "payments awaiting the customer", "url": reverse("staff_payments") + "?status=Unpaid",
         "detail": "Unpaid or failed on open orders"},
        {"count": review, "label": "payments to review", "url": reverse("sales") + "?status=Payment+review",
         "detail": "Paid after the order was cancelled"},
        {"count": low_count, "label": "products low or out of stock", "url": reverse("staff_inventory") + "?low=1",
         "detail": f"{LOW_STOCK} units or fewer"},
    ]

    # Orders placed per day for the last 14 days, drawn as an SVG by hand in the template.
    days = [today - timedelta(days=n) for n in range(13, -1, -1)]
    counts = dict(Order.objects.filter(created__date__gte=days[0]).annotate(day=TruncDate("created"))
                  .values_list("day").annotate(n=Count("pk")))
    series = [counts.get(day, 0) for day in days]
    # The tallest gridline is rounded up to an even number so the middle line lands on a whole number.
    top = max(max(series), 2)
    top += top % 2
    width, height, left, base, ceiling = 480, 190, 30, 160, 18
    slot = (width - left) / len(days)
    chart = {"width": width, "height": height, "left": left, "base": base, "top": top, "bars": [],
             "grid": [{"y": base - (base - ceiling) * step / 2, "label": top * step // 2} for step in range(3)]}
    for index, (day, count) in enumerate(zip(days, series)):
        bar = (base - ceiling) * count / top
        chart["bars"].append({"day": day, "count": count, "x": round(left + index * slot + slot * .18, 1),
                              "w": round(slot * .64, 1), "y": round(base - bar, 1), "h": round(bar, 1),
                              "cx": round(left + index * slot + slot / 2, 1), "today": day == today,
                              "alt": index % 2 == 0})
    return render_staff(request, "store/dashboard.html", "overview", revenue=revenue, status_rows=status_rows,
        needs=needs, quiet=not any(item["count"] for item in needs), chart=chart,
        week_total=sum(series), low_products=low_products.select_related("category").order_by("stock", "name")[:8],
        low_count=low_count, recent=Order.objects.select_related("user", "payment").order_by("-pk")[:8])


# ---- Products ---------------------------------------------------------------

def filtered_products(request):
    """Start with all products and apply the filters selected by staff."""
    products = Product.objects.select_related("category")
    query = request.GET.get("q", "").strip()[:150]
    if query:
        products = products.filter(Q(name__icontains=query) | Q(brand__icontains=query) | Q(variant_label__icontains=query))
    category = request.GET.get("category", "")
    if category.isdigit():
        products = products.filter(category_id=int(category))
    state = request.GET.get("state", "")
    if state in {"available", "hidden"}:
        products = products.filter(available=(state == "available"))
    if request.GET.get("low"):
        products = products.filter(stock__lte=LOW_STOCK)
    return products


@staff_required
def products(request):
    """Searchable, sortable product list."""
    sort = {"name": "name", "price": "-price", "stock": "stock"}.get(request.GET.get("sort"), "-pk")
    page = paginate(request, filtered_products(request).order_by(sort, "pk"))
    return render_staff(request, "store/staff_products.html", "products", page=page,
        categories=Category.objects.order_by("name"), total=Product.objects.count(),
        qs=query_without(request, "page"), sort=request.GET.get("sort", ""))


def product_form_page(request, product=None):
    """Use the same validated form to create a product or edit an existing one."""
    form = StaffProductForm(request.POST or None, request.FILES or None, instance=product)
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        messages.success(request, f"Saved {saved.name}.")
        return redirect("staff_products")
    groups = (Product.objects.exclude(variant_group="").order_by("variant_group")
              .values_list("variant_group", flat=True).distinct())
    ordered = product.orderitem_set.exists() if product else False
    return render_staff(request, "store/staff_product_form.html", "products", form=form, product=product,
                        groups=groups, on_orders=ordered)


@staff_required
def product_new(request):
    return product_form_page(request)


@staff_required
def product_edit(request, pk):
    return product_form_page(request, get_object_or_404(Product, pk=pk))


@staff_required
@require_POST
def product_delete(request, pk):
    """Products on past orders are hidden, not deleted, so order history keeps its link."""
    product = get_object_or_404(Product, pk=pk)
    if OrderItem.objects.filter(product=product).exists():
        Product.objects.filter(pk=pk).update(available=False)
        messages.info(request, f"{product.name} is on past orders, so it was hidden from the shop instead of deleted.")
    else:
        product.delete()
        messages.success(request, f"Deleted {product.name}.")
    return redirect(safe_next(request, reverse("staff_products")))


@staff_required
@require_POST
def product_toggle(request, pk):
    """Hide or show an item in the shop without removing the product record."""
    product = get_object_or_404(Product, pk=pk)
    Product.objects.filter(pk=pk).update(available=not product.available)
    messages.success(request, f"{product.name} is now {'hidden from' if product.available else 'visible in'} the shop.")
    return redirect(safe_next(request, reverse("staff_products")))


# ---- Inventory --------------------------------------------------------------

@staff_required
def inventory(request):
    """List stock levels and counts for products that need attention."""
    items = filtered_products(request).order_by("stock", "name")
    page = paginate(request, items, 30)
    return render_staff(request, "store/staff_inventory.html", "inventory", page=page,
        categories=Category.objects.order_by("name"), low_limit=LOW_STOCK,
        out_count=Product.objects.filter(stock=0).count(),
        low_count=Product.objects.filter(stock__gt=0, stock__lte=LOW_STOCK).count(),
        qs=query_without(request, "page"))


@staff_required
@require_POST
def stock(request, pk):
    """Set the quantity on hand, or add a delivery to it. Whole numbers of zero or more only."""
    product = get_object_or_404(Product, pk=pk)
    adding = "add" in request.POST
    form = (AddStockForm if adding else StockForm)(request.POST)
    ok = form.is_valid()
    if ok:
        value = form.cleaned_data["add" if adding else "quantity"]
        Product.objects.filter(pk=pk).update(stock=F("stock") + value if adding else value)
        product.refresh_from_db()
        message = f"{product.name}: {product.stock} in stock."
    else:
        message = first_error(form)
    if wants_json(request):
        product.refresh_from_db()
        return JsonResponse({"ok": ok, "message": message, "stock": product.stock,
                             "gauge": render_to_string("store/_staff_stock.html", {"product": product})},
                            status=200 if ok else 400)
    (messages.success if ok else messages.error)(request, message)
    return redirect(safe_next(request, reverse("staff_inventory")))


# ---- Categories -------------------------------------------------------------

@staff_required
def categories(request):
    """Show categories and handle the form for adding a new one."""
    form = CategoryForm(request.POST or None, prefix="new")
    if request.method == "POST" and form.is_valid():
        category = form.save()
        messages.success(request, f"Added {category.name}.")
        return redirect("staff_categories")
    rows = Category.objects.annotate(product_count=Count("product")).order_by("name")
    return render_staff(request, "store/staff_categories.html", "categories", rows=rows, form=form)


@staff_required
@require_POST
def category_rename(request, pk):
    """Rename one category after checking the name is not already used."""
    category = get_object_or_404(Category, pk=pk)
    form = CategoryForm(request.POST, instance=category)
    if form.is_valid():
        form.save()
        messages.success(request, f"Renamed to {category.name}.")
    else:
        messages.error(request, f"Could not rename {category.name}. {first_error(form)}")
    return redirect("staff_categories")


@staff_required
@require_POST
def category_delete(request, pk):
    """Remove an empty category only; products must be moved before deleting its category."""
    category = get_object_or_404(Category, pk=pk)
    count = category.product_set.count()
    if count:
        messages.error(request, f"{category.name} still has {count} product{'s' if count != 1 else ''}. "
                                "Move them to another category first, then delete it.")
    else:
        category.delete()
        messages.success(request, f"Deleted {category.name}.")
    return redirect("staff_categories")


# ---- Orders -----------------------------------------------------------------

def filtered_orders(request):
    """Apply the search, order status, payment status and date filters."""
    orders = Order.objects.select_related("user", "payment").annotate(item_count=Count("items"))
    query = request.GET.get("q", "").strip().lstrip("#")[:80]
    for word in query.split():
        match = Q(user__username__icontains=word) | Q(user__first_name__icontains=word) | Q(user__last_name__icontains=word)
        if word.isdigit():
            match |= Q(pk=int(word))
        orders = orders.filter(match)
    status = request.GET.get("status", "")
    if status == "to_fulfil":
        orders = orders.filter(status__in=TO_FULFIL)
    elif status in STATUSES:
        orders = orders.filter(status=status)
    if request.GET.get("payment") in PAYMENT_STATUSES:
        orders = orders.filter(payment__status=request.GET["payment"])
    start, end = date_range(request)
    if start:
        orders = orders.filter(created__date__gte=start)
    if end:
        orders = orders.filter(created__date__lte=end)
    return orders


@staff_required
def sales(request):
    """Show a page of matching orders with counts for the status filters."""
    counts = dict(Order.objects.values_list("status").annotate(n=Count("pk")))
    active = request.GET.get("status", "")
    chips = [{"value": "", "label": "All", "count": sum(counts.values())},
             {"value": "to_fulfil", "label": "Needs action", "count": sum(counts.get(s, 0) for s in TO_FULFIL)}]
    chips += [{"value": s, "label": s, "count": counts.get(s, 0)} for s in STATUSES]
    for chip in chips:
        chip["url"] = with_param(request, "status", chip["value"])
        chip["active"] = chip["value"] == active
    page = paginate(request, filtered_orders(request).order_by("-pk"))
    return render_staff(request, "store/sales.html", "orders", page=page, chips=chips,
        payment_statuses=PAYMENT_STATUSES, qs=query_without(request, "page"))


def can_cancel(order):
    """Staff may cancel only unpaid orders that have no Razorpay order; those go through the payment check instead."""
    return (order.status in {"Pending", "Confirmed", "Processing"}
            and not order.payment.gateway_order and order.payment.status != "Paid")


@staff_required
def sale(request, pk):
    """Show the items, payment and available actions for a single order."""
    order = get_object_or_404(Order.objects.select_related("payment", "user"), pk=pk)
    payment = order.payment
    reached = FLOW.index(order.status) if order.status in FLOW else -1
    steps = [{"name": name, "state": "done" if i < reached else "current" if i == reached else "todo"}
             for i, name in enumerate(FLOW)]
    items = list(order.items.select_related("product"))
    for item in items:
        item.line = item.price * item.quantity
    return render_staff(request, "store/staff_order.html", "orders", order=order, payment=payment, steps=steps,
        items=items, next_status=NEXT.get(order.status),
        can_cancel=can_cancel(order),
        can_cancel_gateway=order.status == "Pending" and payment.method == "Razorpay" and payment.status != "Paid",
        can_recheck=payment.method == "Razorpay" and payment.status != "Paid",
        can_collect=payment.method == "COD" and payment.status != "Paid" and order.status == "Delivered",
        has_gateway_order=payment.gateway_order.startswith("order_"))


@staff_required
@require_POST
@transaction.atomic
def transition(request, pk):
    """Move an order forward, or cancel it when the stored payment state permits."""
    order = get_object_or_404(Order.objects.select_related("payment"), pk=pk)
    target = request.POST.get("status")
    cancel = target == "Cancelled" and can_cancel(order)
    if target and (target == NEXT.get(order.status) or cancel):
        # The update also matches the status we read, so a repeated click cannot return stock twice.
        changed = Order.objects.filter(pk=pk, status=order.status).update(status=target)
        if changed and cancel:
            for item in order.items.all():
                Product.objects.filter(pk=item.product_id).update(stock=F("stock") + item.quantity)
        if changed:
            messages.success(request, f"Order #{pk} is now {target}.")
    else:
        messages.error(request, "This status change is unavailable.")
    return redirect("sale", pk=pk)


@staff_required
@require_POST
@transaction.atomic
def cash_collected(request, pk):
    """Record cash taken at the door. The conditional update makes a repeated click a no-op."""
    changed = Payment.objects.filter(order_id=pk, method="COD", order__status="Delivered").exclude(
        status="Paid").update(status="Paid", reference=f"COD-{pk}")
    if changed:
        messages.success(request, f"Cash collected for order #{pk}. The payment is now Paid.")
    else:
        messages.error(request, "Cash can be recorded only once, for a Cash on delivery order that is Delivered.")
    return redirect("sale", pk=pk)


# ---- Payments ---------------------------------------------------------------

def filtered_payments(request):
    """Apply the same staff-selected filters to the payment screen and CSV export."""
    payments = Payment.objects.select_related("order", "order__user")
    query = request.GET.get("q", "").strip().lstrip("#")[:80]
    for word in query.split():
        match = (Q(reference__icontains=word) | Q(gateway_order__icontains=word) | Q(order__user__username__icontains=word)
                 | Q(order__user__first_name__icontains=word) | Q(order__user__last_name__icontains=word))
        if word.isdigit():
            match |= Q(order_id=int(word))
        payments = payments.filter(match)
    if request.GET.get("status") in PAYMENT_STATUSES:
        payments = payments.filter(status=request.GET["status"])
    if request.GET.get("method"):
        payments = payments.filter(method=request.GET["method"])
    start, end = date_range(request)
    if start:
        payments = payments.filter(order__created__date__gte=start)
    if end:
        payments = payments.filter(order__created__date__lte=end)
    return payments.order_by("-order_id")


@staff_required
def payments(request):
    """Show payment records and totals for the current filter selection."""
    records = filtered_payments(request)
    totals = records.aggregate(count=Count("pk"),
        paid=Sum("order__total", filter=Q(status="Paid")), open=Sum("order__total", filter=~Q(status="Paid")))
    return render_staff(request, "store/staff_payments.html", "payments", page=paginate(request, records),
        totals={"count": totals["count"], "paid": money(totals["paid"]), "open": money(totals["open"])},
        payment_statuses=PAYMENT_STATUSES, methods=Payment.objects.order_by("method").values_list("method", flat=True).distinct(),
        qs=query_without(request, "page"), export_qs=query_without(request, "page"))


def spreadsheet_safe(value):
    """A cell that starts with = + - or @ can run as a formula in a spreadsheet, so quote it."""
    text = str(value)
    return "'" + text if text[:1] in {"=", "+", "-", "@", "\t", "\r"} else text


@staff_required
@require_GET
def payments_csv(request):
    """Download the filtered payments, escaping fields that spreadsheets could treat as formulas."""
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="payments-{timezone.localdate():%Y%m%d}.csv"'
    writer = csv.writer(response)
    writer.writerow(["Order", "Placed (UTC)", "Customer", "Method", "Payment status", "Order status",
                     "Amount (INR)", "Razorpay order id", "Payment reference"])
    for payment in filtered_payments(request).iterator():
        order = payment.order
        writer.writerow([order.pk, order.created.strftime("%Y-%m-%d %H:%M"), spreadsheet_safe(order.user.username),
                         spreadsheet_safe(payment.method), payment.status, order.status, order.total,
                         spreadsheet_safe(payment.gateway_order), spreadsheet_safe(payment.reference)])
    return response


# ---- Customers --------------------------------------------------------------

def customer_queryset():
    """Customers only: staff and administrator accounts never appear here."""
    return User.objects.filter(is_staff=False, is_superuser=False)


@staff_required
def customers(request):
    """List customer accounts and their order totals; staff accounts are excluded."""
    people = customer_queryset().annotate(order_count=Count("order", distinct=True),
        paid_total=Sum("order__total", filter=Q(order__payment__status="Paid")))
    for word in request.GET.get("q", "").split()[:5]:
        people = people.filter(Q(username__icontains=word) | Q(first_name__icontains=word)
                               | Q(last_name__icontains=word) | Q(email__icontains=word))
    state = request.GET.get("state", "")
    if state in {"active", "deactivated"}:
        people = people.filter(is_active=(state == "active"))
    return render_staff(request, "store/staff_customers.html", "customers",
        page=paginate(request, people.order_by("-date_joined", "-pk")), qs=query_without(request, "page"),
        total=customer_queryset().count())


@staff_required
def customer(request, pk):
    """Show and edit one customer’s personal and delivery details together."""
    person = get_object_or_404(customer_queryset(), pk=pk)
    profile = Profile.objects.filter(user=person).first() or Profile(user=person)
    form = StaffCustomerForm(request.POST or None, instance=person)
    delivery = StaffDeliveryForm(request.POST or None, instance=profile)
    if request.method == "POST" and form.is_valid() and delivery.is_valid():
        with transaction.atomic():
            form.save()
            delivery.save()
        messages.success(request, "Customer details saved.")
        return redirect("staff_customer", pk=pk)
    history = Order.objects.filter(user=person).select_related("payment").order_by("-pk")
    paid = history.filter(payment__status="Paid").aggregate(total=Sum("total"), count=Count("pk"))
    return render_staff(request, "store/staff_customer.html", "customers", person=person, form=form,
        delivery=delivery, history=history[:25], order_count=history.count(),
        paid_total=money(paid["total"]), paid_count=paid["count"])


@staff_required
@require_POST
def customer_toggle(request, pk):
    """Enable or disable a customer’s sign-in while keeping their order history."""
    person = get_object_or_404(customer_queryset(), pk=pk)
    User.objects.filter(pk=pk).update(is_active=not person.is_active)
    name = person.get_full_name() or person.username
    messages.success(request, f"{name} can sign in again." if not person.is_active else
                     f"{name} is deactivated and can no longer sign in. Their orders are kept.")
    return redirect("staff_customer", pk=pk)


# ---- Assistant FAQs ---------------------------------------------------------

def faq_page(request, bound=None):
    """Every entry carries its own edit form, so changes happen where the entry is listed."""
    entries = FAQ.objects.order_by("category", "question")
    query = request.GET.get("q", "").strip()[:100]
    if query:
        entries = entries.filter(Q(question__icontains=query) | Q(answer__icontains=query) | Q(category__icontains=query))
    groups = {}
    for entry in entries:
        form = bound if bound is not None and bound.instance.pk == entry.pk else FAQForm(instance=entry, prefix=f"faq{entry.pk}")
        groups.setdefault(entry.category, []).append((entry, form))
    new = bound if bound is not None and bound.instance.pk is None else FAQForm(prefix="new")
    return render_staff(request, "store/staff_faqs.html", "faqs", groups=groups, query=query,
        shown=sum(len(rows) for rows in groups.values()), total=FAQ.objects.count(),
        category_count=FAQ.objects.values("category").distinct().count(), new=new,
        category_names=FAQ.objects.order_by("category").values_list("category", flat=True).distinct(),
        open_pk=bound.instance.pk if bound is not None else None)


@staff_required
def faqs(request):
    """Show assistant answers and accept a new answer from staff."""
    if request.method == "POST":
        form = FAQForm(request.POST, prefix="new")
        if form.is_valid():
            form.save()
            messages.success(request, "Added to the assistant's answers.")
            return redirect("staff_faqs")
        return faq_page(request, form)
    return faq_page(request)


@staff_required
@require_POST
def faq_edit(request, pk):
    """Save one assistant answer after checking the submitted form."""
    entry = get_object_or_404(FAQ, pk=pk)
    form = FAQForm(request.POST, instance=entry, prefix=f"faq{pk}")
    if form.is_valid():
        form.save()
        messages.success(request, "Assistant answer saved.")
        return redirect(reverse("staff_faqs") + f"#faq-{pk}")
    return faq_page(request, form)


@staff_required
@require_POST
def faq_delete(request, pk):
    """Remove an outdated assistant answer after a staff form submission."""
    get_object_or_404(FAQ, pk=pk).delete()
    messages.success(request, "Entry deleted.")
    return redirect("staff_faqs")


# ---- My profile -------------------------------------------------------------

@staff_required
def me(request):
    """Allow a staff member to update their own account details."""
    form = StaffProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Your details are saved.")
        return redirect("staff_me")
    return render_staff(request, "store/staff_me.html", "me", form=form)


@method_decorator(staff_required, name="dispatch")
class PasswordView(PasswordChangeView):
    template_name = "store/staff_password.html"
    form_class = StaffPasswordForm
    success_url = reverse_lazy("staff_me")

    def form_valid(self, form):
        messages.success(self.request, "Your password has been changed.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        return super().get_context_data(section="me", attention=attention_counts(), **kwargs)


# ---- Legacy /staff/manage/ addresses ----------------------------------------

@staff_required
def manage(request, kind, pk=None):
    """Keep old /staff/manage/<kind>/ bookmarks working by showing the matching workspace page."""
    lists = {"products": products, "categories": categories, "faqs": faqs, "customers": customers}
    if kind not in lists:
        raise Http404
    if pk and kind == "products":
        return product_edit(request, pk)
    if pk and kind == "customers":
        return customer(request, pk)
    return lists[kind](request)
