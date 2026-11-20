"""Indian delivery addresses: the fixed state list, field cleaning and one formatted text form.

Profile and Order keep the structured fields and also a formatted `address` text, so receipts,
staff pages and older orders can keep showing a single block of text.
"""
import json
import re
from functools import lru_cache
from pathlib import Path

STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa", "Gujarat", "Haryana",
    "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur",
    "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana",
    "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal",
    # Union territories
    "Andaman and Nicobar Islands", "Chandigarh", "Dadra and Nagar Haveli and Daman and Diu", "Delhi",
    "Jammu and Kashmir", "Ladakh", "Lakshadweep", "Puducherry",
]
COUNTRY = "India"
PIN_RE = re.compile(r"^[1-9][0-9]{5}$")
CITY_RE = re.compile(r"^[A-Za-z][A-Za-z .,'()/-]{1,59}$")
PHONE_MESSAGE = "Enter a 10-digit Indian mobile number, for example 98765 43210."
FIELDS = ["name", "phone", "line1", "line2", "city", "state", "pincode"]


def clean_phone(value):
    """Return the 10 digit mobile number from input such as '+91 98765-43210', or None when it is not one."""
    digits = re.sub(r"[\s().-]", "", value or "")
    digits = re.sub(r"^(\+91|0091|91|0)(?=[0-9]{10}$)", "", digits)
    return digits if re.fullmatch(r"[6-9][0-9]{9}", digits) else None


def format_address(line1="", line2="", city="", state="", pincode=""):
    """Multi-line text for the part of an address that follows the recipient's name."""
    place = ", ".join(part for part in (city, state) if part)
    if pincode:
        place = f"{place} - {pincode}" if place else pincode
    lines = [line1, line2, place, COUNTRY if (line1 or place) else ""]
    return "\n".join(line for line in lines if line)


def pretty_phone(value):
    """9876543210 reads as +91 98765 43210; anything older or odd is shown as saved."""
    value = value or ""
    return f"+91 {value[:5]} {value[5:]}" if re.fullmatch(r"[0-9]{10}", value) else value


@lru_cache(maxsize=1)
def city_map():
    """State to major cities, from the same file the browser loads to fill the City list."""
    path = Path(__file__).resolve().parent / "static" / "store" / "india-cities.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def cities_for(state):
    """List suggested cities for a state; a missing state simply has no suggestions."""
    return city_map().get(state, [])
