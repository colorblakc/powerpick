"""Values every page shell needs: cart count and the category rail."""
from django.urls import reverse
from django.db.models import Count, Q
from .models import Category, Product

# Category order for the Shop menu, from supply to load.
RAIL_ORDER = [
    ("Wires and Cables", "i-cat-cable"),
    ("MCBs and Circuit Protection", "i-cat-mcb"),
    ("Modular Boards", "i-cat-board"),
    ("Switches and Sockets", "i-cat-switch"),
    ("LED Lighting", "i-cat-light"),
    ("Insulation and Accessories", "i-cat-tape"),
    ("Electrical Tools", "i-cat-tool"),
    ("Testers and Measuring Tools", "i-cat-meter"),
]


def shell(request):
    """Prepare menu categories and the cart count that appear throughout the site."""
    cart = request.session.get("cart", {}) if hasattr(request, "session") else {}
    counts = dict(Category.objects.annotate(n=Count("product", filter=Q(product__available=True))).values_list("name", "n"))
    names = list(counts)
    order = [name for name, _ in RAIL_ORDER if name in names] + sorted(n for n in names if n not in dict(RAIL_ORDER))
    icons = dict(RAIL_ORDER)
    current = request.GET.get("category__name", "")
    shop = reverse("catalogue")
    rail = [{"name": name, "icon": icons.get(name, "i-cat-switch"), "url": f"{shop}?category__name={name.replace(' ', '+')}",
             "active": request.path == shop and current == name, "count": counts.get(name, 0)} for name in order]
    brands = list(Product.objects.filter(available=True).exclude(brand="").values_list("brand", flat=True).distinct().order_by("brand")[:12])
    return {"cart_count": sum(int(q) for q in cart.values() if str(q).isdigit()), "rail": rail, "menu_brands": brands}
