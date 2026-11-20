"""Database records for accounts, products, orders, payments and customer content."""
from django.conf import settings
from django.db import models


AVATAR_CHOICES = [(f"{prefix}{number}", f"{label} {number}")
                  for prefix, label in (("m", "Male avatar"), ("f", "Female avatar"))
                  for number in range(1, 6)] + [("b1", "Botpfp portrait")]


class Profile(models.Model):
    """Saved delivery details belong to one login and can change between orders."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    # `address` is the formatted text of the fields below, kept so older code and records still read it.
    address = models.TextField(max_length=500, blank=True)
    phone = models.CharField(max_length=16, blank=True)
    name = models.CharField(max_length=120, blank=True)
    line1 = models.CharField(max_length=120, blank=True)
    line2 = models.CharField(max_length=120, blank=True)
    city = models.CharField(max_length=60, blank=True)
    state = models.CharField(max_length=60, blank=True)
    pincode = models.CharField(max_length=6, blank=True)
    avatar = models.CharField(max_length=2, choices=AVATAR_CHOICES, blank=True, default="")

    @property
    def avatar_filename(self):
        """Allow only known filenames, including when reading an older database row."""
        if self.avatar in dict(AVATAR_CHOICES):
            return f"store/avatars/{self.avatar}.webp"
        return ""


class Category(models.Model):
    name = models.CharField(max_length=80, unique=True)

    def __str__(self):
        return self.name


class Product(models.Model):
    # PROTECT prevents deleting a category that still contains products.
    category = models.ForeignKey(Category, on_delete=models.PROTECT)
    name = models.CharField(max_length=140, unique=True)
    brand = models.CharField(max_length=80)
    description = models.TextField()
    specs = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.PositiveIntegerField(default=0)
    available = models.BooleanField(default=True)
    image = models.ImageField(upload_to="products/", blank=True)
    # Products with the same group name and brand appear together as options.
    variant_group = models.CharField(max_length=140, blank=True, help_text="Use the same group name for options of the same product and brand.")
    variant_label = models.CharField(max_length=80, blank=True, help_text="For example, 2.5 mm² or 4 modules.")

    def __str__(self):
        return self.name


class Order(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    token = models.UUIDField(unique=True)
    # The delivery details are copied here at checkout, so a later move on the profile does not change old orders.
    address = models.TextField()
    phone = models.CharField(max_length=16)
    name = models.CharField(max_length=120, blank=True)
    line1 = models.CharField(max_length=120, blank=True)
    line2 = models.CharField(max_length=120, blank=True)
    city = models.CharField(max_length=60, blank=True)
    state = models.CharField(max_length=60, blank=True)
    pincode = models.CharField(max_length=6, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, default="Pending")
    total = models.DecimalField(max_digits=12, decimal_places=2)


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, null=True, on_delete=models.SET_NULL)
    # A receipt keeps the name and price agreed at purchase time.
    name = models.CharField(max_length=140)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField()


class Payment(models.Model):
    order = models.OneToOneField(Order, on_delete=models.PROTECT)
    method = models.CharField(max_length=12)
    status = models.CharField(max_length=20, default="Unpaid")
    gateway_order = models.CharField(max_length=100, blank=True)
    reference = models.CharField(max_length=100, blank=True)


class FAQ(models.Model):
    # Staff can update the assistant's answers without changing the program.
    category = models.CharField(max_length=80)
    question = models.CharField(max_length=220, unique=True)
    answer = models.TextField()

    def __str__(self):
        return self.question


class Wishlist(models.Model):
    """A customer's saved products, kept separate from the cart."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="wishlist", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, related_name="wishlisted", on_delete=models.CASCADE)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "product"], name="one_wishlist_entry")]
        ordering = ["-created"]


class Review(models.Model):
    """One rating and short note per customer per product."""
    product = models.ForeignKey(Product, related_name="reviews", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField(choices=[(n, str(n)) for n in range(1, 6)])
    title = models.CharField(max_length=80, blank=True)
    body = models.TextField(max_length=1000)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["product", "user"], name="one_review_per_customer")]
        ordering = ["-created"]
