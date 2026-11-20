"""Forms validate customer and staff input before it reaches the database."""
import re

from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, UserCreationForm
from django.contrib.auth.models import User

from .address import CITY_RE, PHONE_MESSAGE, PIN_RE, STATES, cities_for, clean_phone, format_address
from .models import FAQ, Category, Product, Profile, Review


class DeliveryForm(forms.ModelForm):
    """A structured Indian address. `address` is filled with the formatted text so older pages keep working.

    Recipient name, address line 1, state, city, PIN code and phone are always required; only line 2 is optional.
    """
    # A phone number can start with zero, so treat it as text.
    phone = forms.CharField(max_length=20, label="Phone number")
    state = forms.ChoiceField(label="State or UT", choices=[("", "Select state or UT")] + [(s, s) for s in STATES])

    class Meta:
        model = Profile
        fields = ["name", "phone", "line1", "line2", "city", "state", "pincode"]
        labels = {"name": "Full name", "line1": "Address line 1", "line2": "Address line 2", "city": "City",
                  "pincode": "PIN code"}

    required_text = {"name": "Enter the name of the person receiving the order.",
                     "phone": "Enter a mobile number so the delivery can reach you.",
                     "line1": "Enter the house, flat or building for this address.",
                     "city": "Enter or choose the city.", "state": "Choose the state or union territory.",
                     "pincode": "Enter the 6-digit PIN code."}
    # Everything the courier needs; line 2 is the only optional part of the address.
    required_fields = ("name", "phone", "line1", "city", "state", "pincode")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        attrs = {"name": {"autocomplete": "name", "maxlength": 120},
                 "phone": {"autocomplete": "tel-national", "inputmode": "numeric", "maxlength": 20,
                           "placeholder": "98765 43210"},
                 "line1": {"autocomplete": "address-line1", "maxlength": 120, "placeholder": "House or flat number, building"},
                 "line2": {"autocomplete": "address-line2", "maxlength": 120, "placeholder": "Street, area, landmark"},
                 "city": {"autocomplete": "address-level2", "maxlength": 60, "data-addr-city": ""},
                 "state": {"autocomplete": "address-level1", "data-addr-state": ""},
                 "pincode": {"autocomplete": "postal-code", "inputmode": "numeric", "maxlength": 6,
                             "placeholder": "6 digits", "pattern": "[1-9][0-9]{5}"}}
        for name, extra in attrs.items():
            self.fields[name].widget.attrs.update(extra)
        for name, text in self.required_text.items():
            self.fields[name].error_messages["required"] = text
        self.fields["phone"].error_messages["invalid"] = PHONE_MESSAGE
        self.fields["pincode"].error_messages["max_length"] = "Enter a 6-digit PIN code."
        self.fields["state"].error_messages["invalid_choice"] = "Choose a state or union territory from the list."
        for name in self.required_fields:
            self.fields[name].required = True
            self.fields[name].widget.attrs["aria-required"] = "true"
        self.fields["line2"].required = False
        self.fields["city"].widget.attrs["list"] = f"{self['city'].auto_id}_list"

    @property
    def city_options(self):
        return cities_for(self["state"].value() or "")

    def clean_phone(self):
        value = self.cleaned_data.get("phone", "").strip()
        if not value:
            return ""
        number = clean_phone(value)
        if number is None:
            raise forms.ValidationError(PHONE_MESSAGE)
        return number

    def clean_pincode(self):
        value = re.sub(r"\s", "", self.cleaned_data.get("pincode", ""))
        if value and not PIN_RE.match(value):
            raise forms.ValidationError("Enter a 6-digit PIN code that does not start with 0, for example 411001.")
        return value

    def clean_city(self):
        value = " ".join(self.cleaned_data.get("city", "").split())
        if value and not CITY_RE.match(value):
            raise forms.ValidationError("Enter the city name using letters only, for example Pune.")
        return value

    def clean(self):
        cleaned = super().clean()
        for name in ("name", "line1", "line2"):
            if name in cleaned:
                cleaned[name] = " ".join(cleaned[name].split())
        return cleaned

    def formatted_address(self):
        """The single text block saved in `address`, built from the cleaned fields."""
        data = self.cleaned_data
        return format_address(data.get("line1", ""), data.get("line2", ""), data.get("city", ""),
                              data.get("state", ""), data.get("pincode", ""))

    def full_clean(self):
        super().full_clean()
        for name in self.errors:
            if name in self.fields:
                widget = self.fields[name].widget
                widget.attrs["aria-invalid"] = "true"
                widget.attrs["aria-describedby"] = f"{self[name].auto_id}-error"

    def _post_clean(self):
        super()._post_clean()
        if not self.errors:
            self.instance.address = self.formatted_address()


class CustomerForm(forms.ModelForm):
    # Listing fields explicitly keeps account permissions outside this form.
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        group, label = cleaned.get("variant_group"), cleaned.get("variant_label")
        if bool(group) != bool(label):
            raise forms.ValidationError("Enter both a product group and an option label, or leave both blank.")
        if group and label and cleaned.get("category") and cleaned.get("brand"):
            duplicates = Product.objects.filter(category=cleaned["category"], brand__iexact=cleaned["brand"],
                variant_group__iexact=group, variant_label__iexact=label).exclude(pk=self.instance.pk)
            if duplicates.exists():
                raise forms.ValidationError("This option label is already used in this product group.")
        return cleaned

    def clean_price(self):
        price = self.cleaned_data["price"]
        if price <= 0:
            raise forms.ValidationError("Enter a price above zero.")
        return price

    def clean_image(self):
        photo = self.cleaned_data.get("image")
        if photo and getattr(photo, "content_type", None):
            if photo.size > 3_000_000 or photo.image.format not in {"JPEG", "PNG", "WEBP"}:
                raise forms.ValidationError("Choose a JPEG, PNG or WebP under 3 MB.")
        return photo


class ReviewForm(forms.ModelForm):
    """A star rating, an optional headline and a written note of 10 to 1000 characters."""
    rating = forms.TypedChoiceField(choices=[(n, str(n)) for n in range(1, 6)], coerce=int, widget=forms.RadioSelect,
                                    error_messages={"required": "Choose a star rating from 1 to 5."})
    title = forms.CharField(max_length=80, required=False, strip=True,
                            error_messages={"max_length": "Keep the headline to 80 characters or fewer."})
    body = forms.CharField(max_length=1000, strip=True, widget=forms.Textarea(attrs={"rows": 5}),
                           error_messages={"required": "Write a few words about the product (at least 10 characters).",
                                           "max_length": "Keep your review to 1000 characters or fewer."})

    class Meta:
        model = Review
        fields = ["rating", "title", "body"]

    def clean_body(self):
        body = self.cleaned_data["body"]
        if len(body) < 10:
            raise forms.ValidationError(f"Write at least 10 characters. You have written {len(body)}.")
        return body


# ---- Account forms: sign in, registration, profile and password change ----

class StyledFormMixin:
    """Account forms render field by field. This adds input hints and wires errors to inputs for screen readers."""
    hints = {"username": {"autocomplete": "username", "autocapitalize": "none", "spellcheck": "false"},
             "email": {"autocomplete": "email", "autocapitalize": "none", "spellcheck": "false", "inputmode": "email"},
             "first_name": {"autocomplete": "given-name"}, "last_name": {"autocomplete": "family-name"},
             "phone": {"autocomplete": "tel-national", "inputmode": "numeric"},
             "password": {"autocomplete": "current-password"}, "old_password": {"autocomplete": "current-password"},
             "password1": {"autocomplete": "new-password"}, "password2": {"autocomplete": "new-password"},
             "new_password1": {"autocomplete": "new-password"}, "new_password2": {"autocomplete": "new-password"}}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs.update(self.hints.get(name, {}))
            field.widget.attrs.pop("autofocus", None)

    def full_clean(self):
        super().full_clean()
        for name in self.errors:
            if name in self.fields:
                widget = self.fields[name].widget
                widget.attrs["aria-invalid"] = "true"
                widget.attrs["aria-describedby"] = f"{self[name].auto_id}-error"


class LoginForm(StyledFormMixin, AuthenticationForm):
    error_messages = {
        "invalid_login": "That username and password do not match. Check both and try again; the username is case-sensitive.",
        "inactive": "This account is switched off. Contact the shop to have it restored.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Username"
        self.fields["username"].error_messages["required"] = "Enter your username."
        self.fields["password"].error_messages["required"] = "Enter your password."


class RegisterForm(StyledFormMixin, UserCreationForm):
    """Customers only. The field list is explicit, so staff rights can never be posted."""
    first_name = forms.CharField(max_length=150, error_messages={"required": "Enter your first name."})
    last_name = forms.CharField(max_length=150, error_messages={"required": "Enter your last name."})
    email = forms.EmailField(max_length=254, error_messages={"required": "Enter your email address.",
                                                             "invalid": "Enter a valid email address, for example name@example.com."})
    phone = forms.CharField(max_length=20, required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("first_name", "last_name", "email", "username")

    field_order = ["first_name", "last_name", "email", "username", "password1", "password2", "phone"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].label = "Password"
        self.fields["password2"].label = "Confirm password"
        self.fields["password2"].help_text = ""
        self.fields["username"].help_text = "Letters, numbers and @ . + - _ only. You sign in with this."
        self.fields["password2"].error_messages["required"] = "Enter the password again to confirm it."

    def clean_phone(self):
        value = self.cleaned_data.get("phone", "").strip()
        if value and clean_phone(value) is None:
            raise forms.ValidationError(PHONE_MESSAGE)
        return clean_phone(value) or ""

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists. Sign in instead, or use a different email.")
        return email

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("This username is taken. Choose another.")
        return username

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_staff = user.is_superuser = False
        if commit:
            user.save()
            Profile.objects.update_or_create(user=user, defaults={"phone": self.cleaned_data.get("phone", "")})
        return user


class AccountForm(StyledFormMixin, CustomerForm):
    """Personal details on the profile page."""

    class Meta(CustomerForm.Meta):
        pass

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if email and User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Another account already uses this email. Use a different one.")
        return email


class ProfileDeliveryForm(StyledFormMixin, DeliveryForm):
    """The Delivery section of the profile. Its own submission, so the required fields only apply when it is saved."""


class StyledPasswordChangeForm(StyledFormMixin, PasswordChangeForm):
    error_messages = {**PasswordChangeForm.error_messages,
                      "password_incorrect": "Your current password is not right. Re-enter it, checking Caps Lock."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].label = "Current password"
        self.fields["new_password1"].label = "New password"
        self.fields["new_password2"].label = "Confirm new password"
        self.fields["new_password2"].help_text = ""
        self.fields["old_password"].error_messages["required"] = "Enter your current password."


# ---- Staff workspace forms -------------------------------------------------


class StaffFormMixin:
    """Marks invalid fields for screen readers so each error is read with its input."""

    def full_clean(self):
        super().full_clean()
        for name in self.errors:
            if name in self.fields:
                widget = self.fields[name].widget
                widget.attrs["aria-invalid"] = "true"
                widget.attrs["aria-describedby"] = f"id_{self.add_prefix(name)}_errors"


class StaffProductForm(StaffFormMixin, ProductForm):
    remove_image = forms.BooleanField(required=False, label="Remove the current image")

    class Meta(ProductForm.Meta):
        widgets = {
            "image": forms.FileInput(attrs={"accept": "image/jpeg,image/png,image/webp", "data-image-input": ""}),
            "description": forms.Textarea(attrs={"rows": 4}),
            "specs": forms.Textarea(attrs={"rows": 4}),
            "variant_group": forms.TextInput(attrs={"list": "variant-groups", "autocomplete": "off"}),
        }
        error_messages = {"name": {"unique": "Another product already uses this name. Add the rating or pack size to make it distinct."}}

    def save(self, commit=True):
        product = super().save(commit=False)
        if self.cleaned_data.get("remove_image") and not self.files.get("image"):
            product.image = ""
        if commit:
            product.save()
        return product


class CategoryForm(StaffFormMixin, forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name"]
        error_messages = {"name": {"unique": "A category with this name already exists."}}

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        if Category.objects.filter(name__iexact=name).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("A category with this name already exists.")
        return name


class StockForm(forms.Form):
    """A stock level is a whole number from zero up; anything else is refused."""
    quantity = forms.IntegerField(min_value=0, max_value=100000, error_messages={
        "required": "Enter the stock quantity.", "invalid": "Enter a whole number, for example 12.",
        "min_value": "Stock cannot be below zero.", "max_value": "Enter 100000 or fewer."})


class AddStockForm(forms.Form):
    add = forms.IntegerField(min_value=1, max_value=100000, error_messages={
        "required": "Enter how many units arrived.", "invalid": "Enter a whole number, for example 12.",
        "min_value": "Enter 1 or more units to add.", "max_value": "Enter 100000 or fewer."})


class FAQForm(StaffFormMixin, forms.ModelForm):
    class Meta:
        model = FAQ
        fields = ["category", "question", "answer"]
        widgets = {"category": forms.TextInput(attrs={"list": "faq-categories", "autocomplete": "off"}),
                   "answer": forms.Textarea(attrs={"rows": 4})}
        error_messages = {"question": {"unique": "This question already has an entry. Edit that entry instead."}}


class StaffCustomerForm(StaffFormMixin, CustomerForm):
    """Name and email only. Permissions and active state change through their own buttons."""


class StaffDeliveryForm(StaffFormMixin, DeliveryForm):
    # A customer who never saved delivery details can still have their name and email edited: a fully
    # empty address on a profile without one is skipped. Anything entered must be complete.
    def __init__(self, data=None, *args, **kwargs):
        super().__init__(data, *args, **kwargs)
        instance = self.instance
        empty = data is not None and not any((data.get(self.add_prefix(n)) or "").strip() for n in self.fields)
        if empty and not instance.address:
            self.empty_ok = True
            for field in self.fields.values():
                field.required = False
                field.widget.attrs.pop("aria-required", None)
        else:
            self.empty_ok = False

    def _post_clean(self):
        if self.empty_ok:
            return
        super()._post_clean()

    def full_clean(self):
        super().full_clean()
        # The shared address partial names its error elements "<id>-error".
        for name in self.errors:
            if name in self.fields:
                self.fields[name].widget.attrs["aria-describedby"] = f"{self[name].auto_id}-error"


class StaffProfileForm(StaffFormMixin, forms.ModelForm):
    email = forms.EmailField(label="Email address")

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]


class StaffPasswordForm(StaffFormMixin, PasswordChangeForm):
    """Django's own password change form, with its errors marked for screen readers."""
