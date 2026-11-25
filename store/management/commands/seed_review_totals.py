"""College fixture: 10k+ ratings per product plus seven written reviews.

Uses actual rating rows so counts, averages and histograms agree. Seed users
cannot sign in. Repeated execution fills gaps without replacing customer data.
"""
import random

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from store.models import Product, Review

PREFIX = "demo_rating_"
MAX_RATINGS = 11234


class Command(BaseCommand):
    help = "Seed college-demo rating totals and seven written comments per product."

    @transaction.atomic
    def handle(self, *args, **options):
        call_command("seed_reviews", stdout=self.stdout)
        User = get_user_model()
        products = list(Product.objects.filter(available=True).order_by("pk"))
        if not products:
            self.stdout.write("No available products; run seed_demo first.")
            return
        existing = set(User.objects.filter(username__startswith=PREFIX).values_list("username", flat=True))
        User.objects.bulk_create([
            User(username=f"{PREFIX}{i:05d}", is_active=False, password="!")
            for i in range(MAX_RATINGS)
            if f"{PREFIX}{i:05d}" not in existing
        ], batch_size=400)
        users = list(User.objects.filter(username__startswith=PREFIX).order_by("username")
                     .values_list("pk", flat=True)[:MAX_RATINGS])
        added = 0
        for product in products:
            target = 10001 + (product.pk * 137 % 1234)
            have = set(Review.objects.filter(product=product, user_id__in=users)
                       .values_list("user_id", flat=True))
            rng = random.Random(f"powerpick-rating-totals-{product.pk}")
            batch = []
            for user_id in users[:target]:
                rating = rng.choices([5, 4, 3, 2, 1], weights=[60, 27, 8, 3, 2])[0]
                if user_id not in have:
                    batch.append(Review(product=product, user_id=user_id, rating=rating, title="", body=""))
            Review.objects.bulk_create(batch, batch_size=400)
            added += len(batch)
        self.stdout.write(self.style.SUCCESS(f"Added {added} ratings across {len(products)} products."))
