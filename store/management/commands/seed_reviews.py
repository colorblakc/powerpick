"""Add sample reviews for the demo catalogue, from clearly marked demo reviewer accounts.

    python manage.py seed_reviews            (safe to run again, nothing is duplicated)
    python manage.py seed_reviews --clear    (remove the demo reviewers and their reviews only)

Reviewer accounts are inactive with an unusable password, so nobody can sign in as them. The review text is
assembled from sentence pools and filled with each product's own name, brand and specs read from the database.
Results are deterministic: the same catalogue always produces the same reviews.
"""
import random
import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from store.models import Product, Review

PREFIX = "demo_reviewer_"

# (first name, surname, role). Only the surname's first letter is ever shown on the site.
REVIEWERS = [
    ("Rahul", "Sharma", "pro"), ("Priya", "Kulkarni", "home"), ("Amit", "Patil", "pro"),
    ("Anjali", "Deshmukh", "home"), ("Suresh", "Nair", "pro"), ("Sneha", "Joshi", "home"),
    ("Manoj", "Tiwari", "pro"), ("Kavita", "Bhatt", "home"), ("Vikram", "Rathod", "pro"),
    ("Neha", "Gupta", "home"), ("Imran", "Qureshi", "pro"), ("Rohit", "Verma", "home"),
    ("Deepak", "Mehta", "pro"), ("Meera", "Iyer", "home"),
]

# Sentences use {short} (name without the size), {size}, {brand} and the product's own spec values.
# Sentences with a gap for the product are fine to reuse; a rendered sentence is never repeated.
KIND_POS = {
    "pliers": [
        "The {length} length is just right for tight switchboard work, and the {jaws} jaws bite properly on cable ends.",
        "The {grip} are comfortable and stay put even when my hands are sweaty.",
        "Cuts copper strands cleanly and the jaws line up well, with no wobble at the pivot.",
        "A {length} pair sits nicely in my tool bag and does not feel flimsy.",
        "Used it to twist and trim wires through a whole day of conduit work and my palm was not sore.",
        "Jaw teeth hold a screw head or a nut without slipping, which is all I ask from {brand}.",
        "Good heft for {length}, with a neat finish and no rough edges on the handle moulding.",
    ],
    "meter": [
        "Reads {measures} accurately, I cross-checked it against my old meter and the numbers matched.",
        "The {display} display is big and easy to read even in a dim meter room.",
        "Continuity beep is quick, which saves a lot of time when tracing a circuit.",
        "Simple to operate, the dial clicks firmly and the {range} ranging is easy to understand.",
        "Good first meter for checking sockets and fuses at home, the leads feel sturdy.",
        "Used it while fault finding on a mixed-load panel and the readings were steady.",
        "Fits in a shirt pocket yet the screen is clear, a sensible choice from {brand}.",
    ],
    "wire": [
        "Insulation is smooth and the {cross_section} stranded copper pulls easily through conduit.",
        "Wired a whole room with one {coil} coil and had a little left over. Copper looks properly thick.",
        "Strips cleanly without nicking the strands, and the red colour is bright and uniform.",
        "Flexible enough to bend around a junction box without kinking. Good for house wiring.",
        "Used this for the lighting circuit in my flat and the finish looks tidy inside the conduit.",
        "Coil was wound neatly and did not tangle while pulling, which matters on a long run.",
        "Conductor looks like real copper and is bright when stripped, so I am happy with {brand} wire.",
    ],
    "mcb": [
        "Clips onto the DIN rail with a firm click and the toggle feels solid.",
        "Fitted this {rated_current} breaker on a lighting circuit and it has been working without nuisance trips.",
        "Terminal screws are deep and hold the cable well, no loose feeling after tightening.",
        "The trip curve {trip_curve} suits my load, and the ON/OFF positions are marked clearly.",
        "Good build for a single pole breaker, the plastic casing is tight and clean.",
        "Replaced an old breaker with this one in my distribution board and it fitted perfectly.",
        "Easy to wire, the housing has enough room for the conductor to sit straight.",
    ],
    "switch": [
        "The rocker action is smooth and gives a decent click. Looks neat on the wall plate.",
        "Fits the Plane M frame without any gap, and the white finish matches the other modules.",
        "{current} rating is fine for lights and fans, terminals are easy to reach.",
        "Used the {switching} switch for a bedroom light and it has been trouble free.",
        "Screw terminals are deep, so thicker wire sits properly without fraying.",
        "Fitted a few in a new flat and the line-up looks tidy, nothing sticks out.",
        "Good quality plastic that does not feel brittle, and the rocker is quiet.",
    ],
    "socket": [
        "Plug pins go in snugly and do not feel loose. Fits well in the Plane M plate.",
        "The {format} width is good for a standard plate, and the shutters work smoothly.",
        "Used it for a phone charging corner and it holds the plug firmly.",
        "Terminals are roomy and the body is a solid white finish. Good for a {current} load.",
        "Installed one in the study and it looks neat next to the switches.",
    ],
    "bulb": [
        "{output} is bright enough for the whole room, the {colour_temperature} light feels comfortable.",
        "Screwed into the B22 holder easily and has been steady, no flicker at all.",
        "A {power} bulb gives plenty of light for the size, and it stays only a bit warm.",
        "Colour looks natural at {colour_temperature}, not harsh on the eyes in the evening.",
        "Replaced an old incandescent with this and noticed a lower electricity bill already.",
        "Glass is smooth and the cap is neat, no loose fitting in the holder.",
        "Lights up instantly with no humming, which I like in the hall.",
    ],
    "strip": [
        "The {length} strip is flexible, bends around the corners of my false ceiling without trouble.",
        "Colour at {colour_temperature} gives a cosy glow behind the TV panel, and the adhesive sticks well to clean surfaces.",
        "Cut marks are clearly printed so trimming to length is easy, but arrange a {input} supply separately.",
        "Brightness is even along the whole run and no patchy spots.",
        "Used it under kitchen cabinets and it looks tidy and bright.",
    ],
    "box": [
        "Sturdy body, and the {capacity} layout fits modules without any forcing.",
        "Surface mount is easy on a brick wall, the screw holes are positioned well.",
        "White finish matches the Plane M modules and looks clean on the wall.",
        "Used this where chasing was not possible, and the cable entry knockouts open cleanly.",
        "Room inside is enough for wire to sit comfortably behind a {size} plate.",
        "Edges are smooth, nothing sharp to cut the cable insulation.",
        "Fitted it along a staircase wall and the line looked neat and square.",
    ],
    "tape": [
        "Sticks well and unwinds smoothly, and the {width} width wraps neatly around joints.",
        "A {roll_length} roll lasts a good while, and the black PVC looks professional on a finished joint.",
        "Stretches evenly without tearing and stays flat, no lifting at the edges.",
        "Used it on joints in a ceiling fan box and it held firm.",
        "Good grip even on rough wire sheaths, a reasonable tape from {brand}.",
        "PVC feels flexible and does not turn sticky or gummy in the heat.",
    ],
    "drill": [
        "The {battery} battery gives enough runtime for a day of light drilling, and charger is included.",
        "The {chuck} chuck tightens easily and holds the bit without slipping.",
        "Two speed ranges are useful, low for screws and high for drilling in wood.",
        "Light and compact, I can work overhead without getting tired. Good for fixing boxes and clips.",
        "Used it to put up conduit clamps and it handled brick with a proper bit.",
    ],
    "driver": [
        "The {tip} tip fits slotted terminal screws perfectly and the shaft does not bend.",
        "{shaft} shaft is a handy length for switchboard work and the {handle} feels comfortable.",
        "Tip is cleanly ground and has not chewed up any screw heads so far.",
        "Basic but well made screwdriver, tightening panel terminals was easy.",
        "Handy to keep in the kit for the odd terminal screw or socket plate.",
    ],
}

KIND_MIXED = {
    "pliers": ["Does the job but the handle paint wore a little after a month. Jaws are fine.", "Decent for the price. The pivot was slightly stiff at first and loosened up with use."],
    "meter": ["Works well for basic checks but the screen response is a bit slow when the reading changes.", "Accurate enough for home use. I wish the leads were a bit longer."],
    "wire": ["Conductor is fine but the coil needed straightening before pulling. Otherwise good.", "Does the job. Insulation is a little stiff in the cold morning."],
    "mcb": ["Works properly. The toggle is a little firm to press, though that may ease up.", "Fits fine, terminal screws could be slightly bigger."],
    "switch": ["Works well but the click is a bit louder than I expected.", "Fine overall. The rocker feels slightly loose on one piece."],
    "socket": ["Good in general, though the plug is a tight fit at first.", "Okay product. The plate screws could be a bit longer."],
    "bulb": ["Gives good light, I just found it a little bright for a bedroom.", "Bright enough but the colour looked slightly different from my older bulbs."],
    "strip": ["Light is nice, but the adhesive is not strong on a painted wall. I used clips as well.", "Output is fine. The cut points are a bit close together."],
    "box": ["Sturdy but the knockouts are a bit hard to remove without a cutter.", "Does its job, screw holes could be marked more clearly."],
    "tape": ["Works fine, the roll end is hard to find and peel at times.", "Reasonable tape, a bit thinner than the one I normally buy."],
    "drill": ["Fine for light jobs but struggles in thick concrete.", "Compact and handy, battery drains faster with continuous drilling."],
    "driver": ["Good for the price, but the tip is a little soft for tough screws.", "Neat tool, handle could have a bit more grip when wet."],
}
KIND_LOW = {
    "pliers": ["Handle coating started peeling after a few weeks, so I expected a bit more."],
    "meter": ["Reading was jumpy on the resistance range, so I only use it for quick checks."],
    "wire": ["Coil was a little kinked when I opened the pack, not as smooth as I hoped."],
    "mcb": ["Toggle felt stiff and I needed a second try to reset it. Works but not smooth."],
    "switch": ["Rocker feels a bit light and loose on my piece. Works, but I expected a firmer click."],
    "socket": ["Plug was too tight and I had to use force, which I did not like."],
    "bulb": ["Light is okay but it felt dimmer than the lumens printed on the pack."],
    "strip": ["Adhesive peeled off after a few days on my wall, I had to stick it again."],
    "box": ["Plastic feels a bit thin on one corner, I handled it carefully."],
    "tape": ["Edge starts to curl and the glue is weaker than my usual brand."],
    "drill": ["Torque is low for the size, fine for screws but not much else."],
    "driver": ["Tip is not as hard as I expected, it rounded off a stubborn screw."],
}

GENERIC_POS = [
    "Neat packing, the {short} came well protected and looked unused.",
    "Looks exactly like the pictures, and {brand} has given it a clean finish.",
    "Good value for a {short}, I would pay a little more for this quality.",
    "Ordered a second {short} for the next job, which says enough.",
    "Quality is better than the usual loose market stuff. Happy with it.",
    "Recommended for anyone doing small repairs, as the {short} is easy to work with.",
    "Everything about this {short} looks well made and properly finished.",
    "Printed markings on the {short} are clear and easy to read.",
    "The {short} suited my job well, and I will look at more from {brand}.",
    "Price felt fair for what you get with this {short}.",
    "Nothing to complain about so far with the {short}, it has done its job well.",
    "I have been using it for a few weeks now and it still looks new.",
    "Feels reliable. Good product.",
    "Worth it.",
    "Very satisfied.",
    "Perfect for what I needed.",
    "Solid product for the money.",
    "Good buy, no issues.",
    "Fine finish and a sensible price for the {short}.",
    "Better than I expected for this price range.",
]
GENERIC_PRO = [
    "Picked up the {short} for a site job and it did not let me down.",
    "Keeping a spare {short} in my kit now, it has been dependable on jobs.",
    "As an electrician I check small details and this {short} passes, so my customers are happy with the work.",
    "Used it on a flat wiring job last month with no problems.",
    "Told my helper to order the same {short} because it works nicely for contractors.",
]
GENERIC_HOME = [
    "Did a small repair at home myself and the {short} made it simple.",
    "Bought it while renovating our flat and the {short} suited the work well.",
    "My electrician suggested this {brand} {short} and I can see why.",
    "Got it for a weekend fix at home, it was easy to use.",
    "Looks neat and tidy in our house once fitted.",
]
GENERIC_MIXED = [
    "Average experience overall, it works but nothing special.",
    "Does what it says. A few small things could be better.",
    "Good enough for the price, I would not call it outstanding.",
    "The {short} is acceptable, though I have used slightly better.",
    "Fair product. I would buy the {short} again only if the price stays the same.",
    "Usable and fine for light needs, with room for improvement on the {short}.",
    "Not bad, not great. The {short} is simply okay.",
]
GENERIC_LOW = [
    "Disappointed with the {short} in a few small ways, though it does work.",
    "Expected a bit more from {brand}, since it works but I am not fully convinced.",
]

TITLES_POS = ["Good quality", "Works well", "Value for money", "Neat finish", "Happy with it", "Reliable", "Solid build", "Does the job",
              "Recommended", "Very good", "Worth buying", "Good for site work", "Nice product", "Pleased"]
TITLES_MIXED = ["Decent", "Okay for the price", "Average", "Mixed feelings"]
TITLES_LOW = ["Expected better", "Not great"]


def kind_of(name):
    n = name.lower()
    for word, kind in [("pliers", "pliers"), ("multimeter", "meter"), ("house wire", "wire"), ("mcb", "mcb"),
                       ("rocker switch", "switch"), ("socket", "socket"), ("led strip", "strip"), ("led", "bulb"),
                       ("surface box", "box"), ("tape", "tape"), ("drill", "drill"), ("screwdriver", "driver")]:
        if word in n:
            return kind
    return ""


def spec_values(product):
    """Spec lines like 'Length: 180 mm' become {length}; the name gives {short} and {size}."""
    values = {}
    for line in product.specs.splitlines():
        key, _, val = line.partition(":")
        if val.strip():
            values[re.sub(r"\W+", "_", key.strip().lower()).strip("_")] = val.strip()
    short, _, size = product.name.partition("·")
    values.update(short=f"{size.strip()} {short.strip()}".strip(), size=size.strip(), brand=product.brand,
                  handle=values.get("handle", "handle"))
    return values


class Safe(dict):
    """For str.format_map: an unknown {placeholder} stays as plain text instead of raising an error."""
    def __missing__(self, key):
        return key


def fill(template, values):
    """Fill a sentence with this product's values; sentences that need a size are skipped when it has none."""
    if "{size}" in template and not values.get("size"):
        return None
    text = template.format_map(Safe(values))
    return text[0].upper() + text[1:]


def split(text):
    """Break text into sentences so repeats can be spotted across reviews."""
    return re.split(r"(?<=[.!])\s+", text.strip())


def build_for(product, rng, reviewers, used):
    """Pick reviewers, ratings, titles and text for one product. `used` holds sentences already shown elsewhere."""
    count = 7
    for _ in range(200):
        ratings = rng.choices([5, 4, 3, 2], weights=[46, 37, 13, 4], k=count)
        if ratings.count(2) <= 1 and 3.9 <= sum(ratings) / count <= 4.7:
            break
    else:
        ratings = [5, 4, 4, 5, 4, 5, 3][:count]
    kind, values = kind_of(product.name), spec_values(product)
    people = rng.sample(reviewers, count)
    out = []
    for rating, person in zip(sorted(ratings, reverse=True), people):
        role = person.demo_role
        if rating >= 4:
            pools = [KIND_POS.get(kind, []), GENERIC_POS, GENERIC_PRO if role == "pro" else GENERIC_HOME]
            title_pool = TITLES_POS
        elif rating == 3:
            pools = [KIND_MIXED.get(kind, []), GENERIC_MIXED]
            title_pool = TITLES_MIXED
        else:
            pools = [KIND_LOW.get(kind, []), GENERIC_LOW]
            title_pool = TITLES_LOW
        shape = rng.choice(["short", "mid", "mid", "long"]) if rating >= 4 else "mid"
        sentences = []
        wanted = {"short": 1, "mid": 2, "long": 3}[shape]
        order = [0, 1, 2] if shape != "short" else rng.sample([0, 1], 2)
        for index in order:
            if len(sentences) >= wanted:
                break
            if index >= len(pools):
                continue
            for pool in (pools[index], [t for p in pools for t in p]):
                candidates = [c for c in (fill(t, values) for t in pool) if c]
                candidates = [c for c in candidates if not (set(split(c)) & (used | set(sentences)))]
                if candidates:
                    choice = rng.choice(candidates)
                    sentences.append(choice)
                    used.update(split(choice))
                    break
        if not sentences:
            sentences = [fill("an acceptable {short}.", values)]
        title = rng.choice(title_pool) if rng.random() < 0.55 else ""
        out.append((person, rating, title, " ".join(sentences)))
    return out


class Command(BaseCommand):
    help = "Add sample reviews from demo reviewer accounts (idempotent). Use --clear to remove them again."

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true",
                            help="Remove only the demo reviewer accounts and their reviews.")

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        demo = User.objects.filter(username__startswith=PREFIX, is_staff=False, is_superuser=False)
        if options["clear"]:
            reviews = Review.objects.filter(user__in=demo).count()
            accounts = demo.count()
            demo.delete()
            self.stdout.write(f"Removed {accounts} demo reviewer accounts and {reviews} reviews.")
            return

        reviewers = []
        for first, last, role in REVIEWERS:
            user, created = User.objects.get_or_create(
                username=f"{PREFIX}{first.lower()}_{last[0].lower()}",
                defaults=dict(first_name=first, last_name=last, is_active=False))
            if created:
                user.set_unusable_password()
                user.save(update_fields=["password"])
            user.demo_role = role
            reviewers.append(user)

        now = timezone.now()
        added = 0
        used = set()
        for product in Product.objects.filter(available=True).select_related("category").order_by("pk"):
            rng = random.Random(f"powerpick-reviews-{product.pk}")
            for person, rating, title, body in build_for(product, rng, reviewers, used):
                age = timedelta(days=rng.randint(3, 150), hours=rng.randint(0, 23), minutes=rng.randint(0, 59))
                if Review.objects.filter(product=product, user=person).exists():
                    continue
                review = Review.objects.create(product=product, user=person, rating=rating, title=title, body=body)
                # created is auto_now_add, so the spread of dates is applied afterwards.
                Review.objects.filter(pk=review.pk).update(created=now - age)
                added += 1
        self.stdout.write(f"Added {added} reviews from {len(reviewers)} demo reviewers "
                          f"({Review.objects.filter(user__in=reviewers).count()} in total).")
