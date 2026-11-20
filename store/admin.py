"""Make wishlists and reviews searchable in Django’s maintenance admin."""
from django.contrib import admin

from .models import Review, Wishlist


@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display = ("user", "product", "created")
    list_select_related = ("user", "product")
    search_fields = ("user__username", "product__name")


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("product", "user", "rating", "title", "created")
    list_filter = ("rating",)
    list_select_related = ("user", "product")
    search_fields = ("product__name", "user__username", "title", "body")
