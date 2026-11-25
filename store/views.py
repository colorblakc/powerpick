"""Storefront, product discovery, cart and checkout request handlers."""
import json
from decimal import Decimal, InvalidOperation
from typing import NamedTuple
from uuid import uuid4
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction, IntegrityError
from django.db.models import F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.core.files.storage import default_storage
from django.core.paginator import Paginator
from django.db.models import Count, Sum
from django.http import Http404, JsonResponse
from django.utils.http import url_has_allowed_host_and_scheme, urlencode
from .address import FIELDS as ADDRESS_FIELDS
from .forms import DeliveryForm, ReviewForm
from .models import Category, Order, OrderItem, Payment, Product, Profile, Review, Wishlist


CARD_PAGE_SIZE = 24


def _first_spec_line(product):
    """The first non-empty line of a product's specs, shown on cards."""
    for line in (product.specs or "").splitlines():
        if line.strip():
            return line.strip()
    return ""


def decorate_cards(cards, user=None, groups=None):
    """Attach rating, spec line and wishlist state to cards with a fixed number of queries.

    groups maps a card's pk to every product pk its rating should summarise (the
    option pks for a variant group). Cards not listed rate only themselves.
    """
    groups = groups or {}
    all_pks = {pk for card in cards for pk in groups.get(card.pk, [card.pk])}
    totals = {row["product_id"]: row for row in Review.objects.filter(product_id__in=all_pks)
              .values("product_id").annotate(n=Count("id"), total=Sum("rating"))}
    saved = set()
    if user is not None and user.is_authenticated:
        saved = set(Wishlist.objects.filter(user=user, product_id__in=[card.pk for card in cards])
                    .values_list("product_id", flat=True))
    for card in cards:
        count = sum(totals[pk]["n"] for pk in groups.get(card.pk, [card.pk]) if pk in totals)
        total = sum(totals[pk]["total"] for pk in groups.get(card.pk, [card.pk]) if pk in totals)
        card.review_count = count
        card.avg_rating = round(total / count, 1) if count else None
        card.is_saved = card.pk in saved
        card.spec_line = _first_spec_line(card)
    return cards


def catalogue_cards(products, user=None):
    """Show one card for matching options, retaining a real product URL for each card."""
    products = list(products)
    cards = []
    groups = {}
    # Options of one product (same category, brand and group) share a single card; a lone product keys on its pk.
    for product in products:
        key = (product.category_id, product.brand.casefold(), product.variant_group.casefold()) if product.variant_group else (product.pk,)
        groups.setdefault(key, []).append(product)
    # One query finds every available option for all variant groups on the page.
    options = {}
    grouped = [key for key in groups if len(key) == 3]
    if grouped:
        for pk, stock, category_id, brand, group in Product.objects.filter(
                available=True, category_id__in={key[0] for key in grouped}).exclude(variant_group="").values_list(
                "pk", "stock", "category_id", "brand", "variant_group"):
            options.setdefault((category_id, brand.casefold(), group.casefold()), []).append((pk, stock))
    rating_groups = {}
    for key, matching in groups.items():
        # The card opens the option whose price it displays, even after sorting.
        product = min(matching, key=lambda item: (item.price, item.pk))
        if product.variant_group:
            found = options.get(key, [])
            product.option_count = len(found)
            product.from_price = product.price
            product.any_stock = any(stock for _, stock in found)
            rating_groups[product.pk] = [pk for pk, _ in found] or [product.pk]
        cards.append(product)
    return decorate_cards(cards, user, rating_groups)


def ordered_categories():
    """Categories in single-line order (supply to load) with their available product counts."""
    from .context import RAIL_ORDER
    icons = dict(RAIL_ORDER)
    order = [name for name, _ in RAIL_ORDER]
    rows = list(Category.objects.annotate(count=Count("product", filter=Q(product__available=True))))
    rows.sort(key=lambda c: (order.index(c.name) if c.name in order else len(order), c.name))
    for row in rows:
        row.icon = icons.get(row.name, "i-cat-switch")
    return rows


def _query_string(request, *drop):
    """The current query string without the named keys and without paging."""
    params = request.GET.copy()
    for key in (*drop, "page"):
        params.pop(key, None)
    return params.urlencode()


def catalogue(request, home=False):
    """Build one catalogue query, narrowing it only when a shopper selects a filter."""
    products = Product.objects.filter(available=True).select_related("category")
    query = request.GET.get("q", "").strip()[:150]
    chips = []
    shop = reverse("catalogue")

    def chip(label, *keys):
        rest = _query_string(request, *keys)
        chips.append({"label": label, "url": f"{shop}?{rest}" if rest else shop})

    if query:
        products = products.filter(Q(name__icontains=query) | Q(description__icontains=query) |
                                   Q(brand__icontains=query) | Q(specs__icontains=query) |
                                   Q(variant_group__icontains=query) | Q(variant_label__icontains=query))
        chip(f"Search: {query}", "q")
    for field, name in (("category__name", "Category"), ("brand", "Brand")):
        if request.GET.get(field):
            products = products.filter(**{field: request.GET[field]})
            chip(f"{name}: {request.GET[field]}", field)
    for param, lookup, label in (("min", "price__gte", "From"), ("max", "price__lte", "Up to")):
        try:
            value = Decimal(request.GET.get(param, ""))
            if value.is_finite() and 0 <= value <= 99999999:
                products = products.filter(**{lookup: value})
                chip(f"{label} ₹{value.normalize():f}", param)
        except InvalidOperation:
            pass
    in_stock_only = request.GET.get("instock") == "1"
    if in_stock_only:
        products = products.filter(stock__gt=0)
        chip("In stock only", "instock")
    sort = {"low": "price", "high": "-price", "name": "name"}.get(request.GET.get("sort"), "pk")
    cards = catalogue_cards(products.order_by(sort), request.user)
    # A card shows its cheapest option, which may differ from the row the database sorted on, so sort again.
    if request.GET.get("sort") in {"low", "high"}:
        cards.sort(key=lambda item: item.price, reverse=request.GET.get("sort") == "high")
    paginator = Paginator(cards, CARD_PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))
    page_query = _query_string(request)
    heading = request.GET.get("category__name") or (f"{request.GET['brand']} products" if request.GET.get("brand") else "All products")
    return render(request, "store/catalogue.html", dict(
        products=page.object_list, page=page, paginator=paginator, total=paginator.count,
        page_range=list(paginator.get_elided_page_range(page.number, on_each_side=1, on_ends=1)),
        page_query=page_query + "&" if page_query else "", chips=chips, query=query, heading=heading,
        categories=ordered_categories(), in_stock_only=in_stock_only,
        brands=Product.objects.filter(available=True).order_by("brand").values_list("brand", flat=True).distinct(),
        home=home))


def home(request):
    """Landing page: search-led hero, product photography, in-stock products and real catalogue facts."""
    categories = ordered_categories()
    available = Product.objects.filter(available=True)
    stocked = catalogue_cards(available.filter(stock__gt=0).select_related("category").order_by("pk"), request.user)
    # Take products round-robin across categories so the row shows the range, not one aisle.
    lanes = {}
    for card in stocked:
        lanes.setdefault(card.category_id, []).append(card)
    featured = []
    while len(featured) < 8 and any(lanes.values()):
        for lane in lanes.values():
            if lane and len(featured) < 8:
                featured.append(lane.pop(0))
    # Each category tile borrows the photo of a real product in it.
    photos = {}
    for category_id, name, image in available.exclude(image="").order_by("pk").values_list("category_id", "name", "image"):
        photos.setdefault(category_id, (default_storage.url(image), name))
    for category in categories:
        category.photo, category.photo_alt = photos.get(category.pk, ("", ""))
    last_order = Order.objects.filter(user=request.user).order_by("-pk").first() if request.user.is_authenticated else None
    return render(request, "store/home.html", dict(
        categories=categories, featured=featured, hero_tiles=[card for card in featured if card.image][:4],
        last_order=last_order, brands=list(available.values("brand").annotate(count=Count("id")).order_by("brand")),
        listed=available.count(), in_stock=available.filter(stock__gt=0).count()))


def _same_site(request, target):
    """Return target only when it is a path on this site, so a forged next cannot redirect away."""
    if target and url_has_allowed_host_and_scheme(target, {request.get_host()}, require_https=request.is_secure()):
        return target
    return ""


@require_POST
def wishlist_toggle(request, pk):
    """Save or remove one product. Plain posts redirect back; fetch requests get JSON."""
    wants_json = request.headers.get("X-Requested-With") == "fetch"
    target = (_same_site(request, request.POST.get("next")) or _same_site(request, request.META.get("HTTP_REFERER", ""))
              or reverse("wishlist"))
    if not request.user.is_authenticated:
        login_url = f"{reverse('login')}?{urlencode({'next': target})}"
        if wants_json:
            return JsonResponse({"ok": False, "login": login_url, "message": "Sign in to save products."}, status=401)
        messages.info(request, "Sign in to save products to your wishlist.")
        return redirect(login_url)
    product = get_object_or_404(Product, pk=pk)
    entry = Wishlist.objects.filter(user=request.user, product=product)
    state = request.POST.get("state")
    saved = entry.exists()
    message = ""
    if request.POST.get("move") == "cart":
        # Moving to the cart keeps the server's stock check; the entry leaves the wishlist either way.
        basket = request.session.get("cart", {})
        wanted = basket.get(str(pk), 0) + 1
        if product.available and wanted <= product.stock:
            basket[str(pk)] = wanted
            request.session["cart"] = basket
            request.session.pop("checkout_token", None)
            entry.delete()
            saved = False
            message = f"{product.name} moved to your cart."
        else:
            message = f"{product.name} is out of stock, so it stays on your wishlist."
            if wants_json:
                return JsonResponse({"ok": False, "message": message}, status=409)
            messages.error(request, message)
            return redirect(target)
    else:
        want_saved = {"add": True, "remove": False}.get(state, not saved)
        if want_saved and not product.available:
            raise Http404
        if want_saved and not saved:
            Wishlist.objects.get_or_create(user=request.user, product=product)
        elif not want_saved and saved:
            entry.delete()
        saved = want_saved
        message = f"{product.name} saved to your wishlist." if saved else f"{product.name} removed from your wishlist."
    count = Wishlist.objects.filter(user=request.user).count()
    if wants_json:
        return JsonResponse({"ok": True, "wishlisted": saved, "count": count, "message": message})
    messages.success(request, message)
    return redirect(target)


@login_required
def wishlist(request):
    """The signed-in customer's saved products that are still on sale."""
    saved = Wishlist.objects.filter(user=request.user, product__available=True).select_related("product__category")
    items = decorate_cards([entry.product for entry in saved], request.user)
    return render(request, "store/wishlist.html", dict(items=items))


REVIEW_ORDER_STATUSES = ("Confirmed", "Processing", "Shipped", "Delivered")
RECENT_LIMIT = 6


def parse_specs(text):
    """Split "Label: value" lines into rows; lines without a usable label become notes."""
    rows, notes = [], []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        label, sep, value = line.partition(":")
        label, value = label.strip(), value.strip()
        if sep and label and value and len(label) <= 40:
            rows.append((label, value))
        else:
            notes.append(line)
    return rows, notes


def reviewer_name(user):
    """First name and last initial only, so a review never exposes a username or email."""
    first = user.first_name.strip()
    last = user.last_name.strip()
    if not first:
        return "Customer"
    return f"{first} {last[0].upper()}." if last else first


def option_ids(product):
    """Every available option of the same product and brand. Reviews are shared across them, as on the cards."""
    if not product.variant_group:
        return [product.pk]
    ids = list(Product.objects.filter(category_id=product.category_id, brand__iexact=product.brand,
                                      variant_group__iexact=product.variant_group).values_list("pk", flat=True))
    return ids or [product.pk]


def can_review(user, product):
    """Only a customer with a paid, confirmed-or-later order for this product may review it."""
    if not user.is_authenticated or user.is_staff:
        return False
    return OrderItem.objects.filter(order__user=user, product_id__in=option_ids(product),
                                    order__status__in=REVIEW_ORDER_STATUSES, order__payment__status="Paid").exists()


def review_summary(ids):
    """Average, count and per-star percentages for the reviews of these product ids."""
    rows = Review.objects.filter(product_id__in=ids).values("rating").annotate(n=Count("id"))
    counts = {star: 0 for star in range(1, 6)}
    counts.update({row["rating"]: row["n"] for row in rows})
    count = sum(counts.values())
    bars = [dict(star=star, count=counts[star], percent=round(100 * counts[star] / count) if count else 0)
            for star in (5, 4, 3, 2, 1)]
    average = round(sum(star * n for star, n in counts.items()) / count, 1) if count else None
    return dict(count=count, average=average, rounded=round(average) if average else 0, bars=bars)


def detail(request, pk, review_form=None):
    """Product page. A review post with errors comes back here so the form keeps what was typed."""
    product = get_object_or_404(Product.objects.select_related("category"), pk=pk, available=True)
    variants = Product.objects.none()
    related = Product.objects.filter(category=product.category, available=True).exclude(pk=pk)
    if product.variant_group:
        variants = Product.objects.filter(category=product.category, brand__iexact=product.brand,
                                           variant_group__iexact=product.variant_group, available=True).order_by("price", "pk")
        related = related.exclude(pk__in=variants.values("pk"))
    # Recently viewed: the newest six ids live in the session; the current product is not listed back to itself.
    seen = [i for i in request.session.get("recent", []) if isinstance(i, int)]
    by_id = Product.objects.filter(pk__in=seen, available=True).in_bulk()
    recent = [by_id[i] for i in seen if i != pk and i in by_id]
    request.session["recent"] = ([pk] + [i for i in seen if i != pk])[:RECENT_LIMIT]

    rows, notes = parse_specs(product.specs)
    ids = option_ids(product)
    summary = review_summary(ids)
    reviews = list(Review.objects.filter(product_id__in=ids).exclude(body="").select_related("user", "product")[:7])
    for review in reviews:
        review.name = reviewer_name(review.user)
        review.is_seeded = review.user.username.startswith("demo_reviewer_")
    user = request.user
    own = Review.objects.filter(product_id__in=ids, user=user).first() if user.is_authenticated else None
    eligible = can_review(user, product)
    in_cart = int(request.session.get("cart", {}).get(str(pk), 0) or 0)
    saved = user.is_authenticated and Wishlist.objects.filter(user=user, product=product).exists()
    others_in_stock = any(v.stock for v in variants if v.pk != pk)
    image_url = request.build_absolute_uri(product.image.url) if product.image else None
    schema = {"@context": "https://schema.org", "@type": "Product", "name": product.name,
              "description": product.description[:500], "brand": {"@type": "Brand", "name": product.brand},
              "category": product.category.name,
              "offers": {"@type": "Offer", "priceCurrency": "INR", "price": str(product.price),
                         "url": request.build_absolute_uri(request.path),
                         "availability": "https://schema.org/InStock" if product.stock else "https://schema.org/OutOfStock"}}
    if image_url:
        schema["image"] = image_url
    if summary["count"]:
        schema["aggregateRating"] = {"@type": "AggregateRating", "ratingValue": str(summary["average"]),
                                     "reviewCount": summary["count"], "bestRating": "5", "worstRating": "1"}
    return render(request, "store/detail.html", dict(
        product=product, variants=variants, variant_count=len(variants), stars=(1, 2, 3, 4, 5), related=catalogue_cards(related, request.user)[:4],
        recent=recent, spec_rows=rows, spec_notes=notes, glance=rows[:3] if len(rows) >= 3 else [],
        summary=summary, reviews=reviews, own_review=own, can_review=eligible, review_form=review_form or ReviewForm(),
        in_cart=in_cart, room=max(product.stock - in_cart, 0), saved=saved, others_in_stock=others_in_stock,
        schema_json=json.dumps(schema, ensure_ascii=False).replace("<", "\\u003c")))


@require_POST
def add_review(request, pk):
    product = get_object_or_404(Product, pk=pk, available=True)
    back = redirect(reverse("detail", args=[pk]) + "#reviews")
    if not request.user.is_authenticated:
        return redirect(f"{reverse('login')}?next={reverse('detail', args=[pk])}%23reviews")
    if request.user.is_staff:
        messages.error(request, "Staff accounts cannot review products.")
        return back
    if not can_review(request.user, product):
        messages.error(request, "Only customers with a paid order for this product can review it.")
        return back
    if Review.objects.filter(product_id__in=option_ids(product), user=request.user).exists():
        messages.info(request, "You have already reviewed this product. Delete your review to write a new one.")
        return back
    form = ReviewForm(request.POST)
    if not form.is_valid():
        return detail(request, pk, review_form=form)
    try:
        with transaction.atomic():
            review = form.save(commit=False)
            review.product, review.user = product, request.user
            review.save()
    except IntegrityError:
        messages.info(request, "You have already reviewed this product.")
        return back
    messages.success(request, "Thanks. Your review is now on this page.")
    return back


@require_POST
def delete_review(request, pk):
    """Remove the signed-in customer's own review of this product (or of any of its options)."""
    if not request.user.is_authenticated:
        return redirect(f"{reverse('login')}?next={reverse('detail', args=[pk])}%23reviews")
    # Filtering by the signed-in user means nobody can delete another customer's review.
    product = get_object_or_404(Product, pk=pk)
    deleted, _ = Review.objects.filter(product_id__in=option_ids(product), user=request.user).delete()
    if deleted:
        messages.success(request, "Your review was deleted.")
    else:
        messages.error(request, "There is no review of yours on this product.")
    return redirect(reverse("detail", args=[pk]) + "#reviews")


class CartLine(NamedTuple):
    """One basket row. Checkout unpacks it as (product, quantity, subtotal)."""
    product: Product
    quantity: int
    subtotal: Decimal

    @property
    def unavailable(self):
        return not self.product.available or self.product.stock < 1

    @property
    def over_stock(self):
        return not self.unavailable and self.quantity > self.product.stock

    @property
    def blocked(self):
        """A blocked line cannot be ordered until the customer changes or removes it."""
        return self.unavailable or self.over_stock


def cart_lines(request):
    """Basket rows and their total. Only quantities live in the session; prices always come from the database."""
    basket = request.session.get("cart", {})
    products = Product.objects.filter(pk__in=basket).order_by("name")
    lines = [CartLine(p, int(basket[str(p.pk)]), p.price * int(basket[str(p.pk)])) for p in products]
    missing = set(basket) - {str(product.pk) for product in products}
    if missing:
        # Tell the customer before checkout if a product was removed by staff.
        request.session["cart"] = {key: quantity for key, quantity in basket.items() if key not in missing}
        request.session.pop("checkout_token", None)
        messages.warning(request, "An item is no longer available and was removed from your cart. Please review your order.")
    return lines, sum((line[2] for line in lines), Decimal("0.00")), bool(missing)


def cart(request):
    """The basket page, with every line re-priced from the database."""
    lines, total, _ = cart_lines(request)
    return render(request, "store/cart.html", dict(
        lines=lines, total=total, item_count=sum(line.quantity for line in lines),
        blocked_count=sum(1 for line in lines if line.blocked)))


class CartError(Exception):
    """A cart change that was refused. The text tells the customer how to fix it."""


def _apply_cart_change(request, product, basket, action):
    """Validate one cart change against stock, store it in the session and return a short message."""
    key, name = str(product.pk), product.name
    have = int(basket.get(key, 0))
    if action not in {"add", "set", "remove"}:
        raise CartError("That cart action is not available. Reload the page and try again.")
    added = 0
    if action == "remove":
        quantity = 0
    else:
        raw = str(request.POST.get("quantity", "1")).strip()
        if not (raw.isascii() and raw.isdigit()) or len(raw) > 4:
            raise CartError("Enter the quantity as a whole number, 1 or higher.")
        quantity = added = int(raw)
        if action == "add":
            if quantity < 1:
                raise CartError("Choose at least 1 to add to your cart.")
            quantity += have
    if quantity > 999:
        raise CartError("The most you can order at once is 999. Choose a smaller quantity.")
    if quantity:
        if not product.available:
            raise CartError(f"{name} is no longer available.")
        if product.stock < 1:
            raise CartError(f"{name} is out of stock.")
        # Lowering a quantity that is already above stock is allowed, since it moves toward a valid order.
        if quantity > product.stock and not (action == "set" and quantity <= have):
            if action == "add" and have:
                room = max(product.stock - have, 0)
                hint = f" Add {room} or fewer." if room else ""
                raise CartError(f"Only {product.stock} of {name} in stock and {have} already in your cart.{hint}")
            raise CartError(f"Only {product.stock} of {name} in stock. Choose {product.stock} or fewer.")
        basket[key] = quantity
    else:
        basket.pop(key, None)
    request.session["cart"] = basket
    # Any basket change starts a new checkout, so an old token can never match a different basket.
    request.session.pop("checkout_token", None)
    if action == "add":
        return f"Added {added} × {name} to your cart"
    if not quantity:
        return f"Removed {name} from your cart"
    return f"Updated {name} to {quantity} in your cart"


@require_POST
def change_cart(request, pk):
    """Add, set or remove one product. Fetch callers (X-Requested-With: fetch) get JSON, others a redirect."""
    product = get_object_or_404(Product, pk=pk)
    basket = dict(request.session.get("cart", {}))
    action = request.POST.get("action") or "set"
    if action == "update":  # an older name for "set"
        action = "set"
    try:
        message, ok = _apply_cart_change(request, product, basket, action), True
    except CartError as exc:
        message, ok = str(exc), False
    if request.headers.get("X-Requested-With") == "fetch":
        lines, total, _ = cart_lines(request)
        mine = next((line for line in lines if line.product.pk == product.pk), None)
        return JsonResponse({
            "ok": ok, "message": message, "total": str(total),
            "count": sum(int(q) for q in request.session.get("cart", {}).values()),
            "line_total": str(mine.subtotal) if mine else "0.00",
            "quantity": mine.quantity if mine else 0,
            "stock": product.stock, "available": product.available and product.stock > 0,
        }, status=200 if ok else 400)
    (messages.success if ok else messages.error)(request, message)
    return redirect(_same_site(request, request.POST.get("next", "")) or reverse("cart"))


def _resume_order(order):
    """Send a repeated submit to the page that still has something to do for this order."""
    if order.status == "Pending":
        return redirect("gateway_page", pk=order.pk)
    return redirect("order_detail", pk=order.pk)


def _delivery_form(request, saved):
    """The delivery form, starting from the saved profile and the account's own name."""
    initial = {}
    if not (saved and saved.name):
        initial["name"] = request.user.get_full_name().strip()
    return DeliveryForm(request.POST or None, instance=saved, initial=initial)


PAYMENT_METHODS = ("COD", "Razorpay")


@login_required
def checkout(request):
    lines, total, missing = cart_lines(request)
    if missing:
        return redirect("cart")
    token = request.session.setdefault("checkout_token", str(uuid4()))
    if request.method == "POST":
        previous = Order.objects.filter(user=request.user, token=token).first()
        if previous and request.POST.get("token") == token:
            return _resume_order(previous)
    if not lines:
        return redirect("cart")
    if any(line.blocked for line in lines):
        messages.error(request, "Some items are out of stock or above the available quantity. Fix them in your cart to continue.")
        return redirect("cart")
    saved = Profile.objects.filter(user=request.user).first()
    delivery = _delivery_form(request, saved)
    save_details = bool(request.POST.get("save_details")) if request.method == "POST" else not (saved and saved.line1)
    method = request.POST.get("method") if request.method == "POST" else "Razorpay"
    changed_from = None
    if request.method == "POST" and delivery.is_valid():
        try:
            seen = Decimal(request.POST.get("expected_total", ""))
        except InvalidOperation:
            seen = None
        if seen is not None and seen != total:
            # Prices or stock moved after this page was drawn. Show the new total before anything is reserved.
            changed_from = seen
        elif request.POST.get("token") != token or method not in PAYMENT_METHODS:
            messages.error(request, "Review your current basket and payment choice.")
        else:
            try:
                # If any item sells out, Django reverses every change in this block.
                with transaction.atomic():
                    # Cash on delivery needs no payment step, so the order is confirmed and goes straight to staff.
                    order = Order.objects.create(user=request.user, token=token, total=total,
                        address=delivery.formatted_address(), status="Confirmed" if method == "COD" else "Pending",
                        **{name: delivery.cleaned_data[name] for name in ADDRESS_FIELDS})
                    for product, qty, _ in lines:
                        updated = Product.objects.filter(pk=product.pk, available=True, stock__gte=qty,
                            price=product.price).update(stock=F("stock") - qty)
                        if not updated:
                            raise ValueError
                        OrderItem.objects.create(order=order, product=product, name=product.name,
                                                 price=product.price, quantity=qty)
                    Payment.objects.create(order=order, method=method)
            except IntegrityError:
                existing = Order.objects.filter(user=request.user, token=token).first()
                if existing:
                    return _resume_order(existing)
                raise
            except ValueError:
                messages.error(request, "Stock or pricing changed while you were checking out. Review your cart, then try again.")
                return redirect("cart")
            if save_details:
                Profile.objects.update_or_create(user=request.user, defaults=dict(
                    address=delivery.formatted_address(), **{name: delivery.cleaned_data[name] for name in ADDRESS_FIELDS}))
            request.session["cart"] = {}
            if method == "COD":
                messages.success(request, f"Order #{order.pk} is confirmed. Pay ₹{order.total:,.2f} in cash when it is delivered.")
                return redirect(reverse("order_detail", args=[order.pk]) + "?placed=1")
            return redirect("gateway_page", pk=order.pk)
    return render(request, "store/checkout.html", dict(
        form=delivery, method=method, lines=lines, total=total, token=token, save_details=save_details, changed_from=changed_from,
        item_count=sum(line.quantity for line in lines)))
