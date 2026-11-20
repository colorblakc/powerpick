"""Connect each website address to the Django view that handles it."""
from django.conf import settings
from django.contrib import admin
from django.contrib.auth import views as auth
from django.contrib.auth.decorators import login_required
from django.views.generic import RedirectView
from django.urls import include, path, re_path
from django.views.static import serve
from django.views.decorators.http import require_POST
from store import accounts, chat, pages, staff, views

# Each address maps to the function that reads or changes its part of the shop.
urlpatterns = [
    path("", views.home, name="home"),
    path("shop/", views.catalogue, name="catalogue"),
    path("wishlist/", views.wishlist, name="wishlist"),
    path("wishlist/toggle/<int:pk>/", views.wishlist_toggle, name="wishlist_toggle"),
    path("products/<int:pk>/", views.detail, name="detail"),
    path("products/<int:pk>/review/", views.add_review, name="add_review"),
    path("products/<int:pk>/review/delete/", views.delete_review, name="delete_review"),
    path("accounts/register/", accounts.register, name="register"),
    path("accounts/login/", accounts.StoreLoginView.as_view(), name="login"),
    path("accounts/logout/", require_POST(auth.LogoutView.as_view()), name="logout"),
    path("accounts/password/", login_required(accounts.StorePasswordChangeView.as_view()), name="password_change"),
    path("accounts/password/done/", accounts.password_change_done, name="password_change_done"),
    path("account/", accounts.profile, name="profile"),
    path("account/avatar/", accounts.update_avatar, name="update_avatar"),
    path("cart/", views.cart, name="cart"),
    path("cart/<int:pk>/", views.change_cart, name="change_cart"),
    path("checkout/", views.checkout, name="checkout"),
    path("orders/", accounts.orders, name="orders"),
    path("orders/<int:pk>/", accounts.order_detail, name="order_detail"),
    path("orders/<int:pk>/receipt/", accounts.receipt, name="receipt"),
    path("orders/<int:pk>/cancel/", accounts.cancel_cod, name="order_cancel"),
    path("orders/<int:pk>/reorder/", accounts.reorder, name="reorder"),
    path("payment-history/", accounts.orders, {"payments": True}, name="history"),
    path("payments/", include("store.gateway_urls")),
    path("assistant/ask/", chat.ask, name="chat_ask"),
    path("staff/", staff.dashboard, name="dashboard"),
    path("staff/products/", staff.products, name="staff_products"),
    path("staff/products/new/", staff.product_new, name="staff_product_new"),
    path("staff/products/<int:pk>/", staff.product_edit, name="staff_product_edit"),
    path("staff/products/<int:pk>/delete/", staff.product_delete, name="staff_product_delete"),
    path("staff/products/<int:pk>/toggle/", staff.product_toggle, name="staff_product_toggle"),
    path("staff/inventory/", staff.inventory, name="staff_inventory"),
    path("staff/inventory/<int:pk>/stock/", staff.stock, name="staff_stock"),
    path("staff/categories/", staff.categories, name="staff_categories"),
    path("staff/categories/<int:pk>/rename/", staff.category_rename, name="staff_category_rename"),
    path("staff/categories/<int:pk>/delete/", staff.category_delete, name="staff_category_delete"),
    path("staff/sales/", staff.sales, name="sales"),
    path("staff/sales/<int:pk>/", staff.sale, name="sale"),
    path("staff/sales/<int:pk>/update/", staff.transition, name="transition"),
    path("staff/sales/<int:pk>/cash/", staff.cash_collected, name="cash_collected"),
    path("staff/payments/", staff.payments, name="staff_payments"),
    path("staff/payments/export.csv", staff.payments_csv, name="staff_payments_csv"),
    path("staff/customers/", staff.customers, name="staff_customers"),
    path("staff/customers/<int:pk>/", staff.customer, name="staff_customer"),
    path("staff/customers/<int:pk>/toggle/", staff.customer_toggle, name="staff_customer_toggle"),
    path("staff/faqs/", staff.faqs, name="staff_faqs"),
    path("staff/faqs/<int:pk>/", staff.faq_edit, name="staff_faq_edit"),
    path("staff/faqs/<int:pk>/delete/", staff.faq_delete, name="staff_faq_delete"),
    path("staff/profile/", staff.me, name="staff_me"),
    path("staff/profile/password/", staff.PasswordView.as_view(), name="staff_password"),
    path("staff/manage/<str:kind>/", staff.manage, name="manage"),
    path("staff/manage/<str:kind>/<int:pk>/", staff.manage, name="edit"),
    path("help/<slug:slug>/", pages.page, name="page"),
    path("robots.txt", pages.robots_txt, name="robots"),
    path("admin/login/", RedirectView.as_view(url="/accounts/login/?next=/admin/", query_string=False)),
    path("admin/", admin.site.urls),
    # Product photos are served by the app itself so a single container needs no extra web server.
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
]

handler404 = "store.pages.not_found"
handler403 = "store.pages.permission_denied"
handler500 = "store.pages.server_error"

admin.site.site_header = "Power Pick admin"
admin.site.site_title = "Power Pick admin"
admin.site.index_title = "Store data"
