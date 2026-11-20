"""Load the starter catalogue and FAQ articles without resetting shop records."""
import hashlib
import json

from django.conf import settings
from django.core.files import File
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from store.models import Category, FAQ, Product


# SHA-1 digests (first 12 hex characters) of answers seeded by earlier versions of knowledge/faq_seed.md.
# An FAQ row whose answer still matches one of these has not been edited by staff, so the command may
# refresh it from the current seed, or retire it when the question is no longer in the seed. Rows staff
# have edited never match and are left alone. When you rewrite a seeded answer, add its old digest here
# (the answer text as it was before the rewrite, so rows still carrying it are refreshed).
LEGACY_ANSWERS = {
    'How do I register for a Power Pick account?': 'd5e2ca47a629',
    'Why does registration reject my username?': '79ca945d2c7d',
    'Why was my new password rejected?': '7f42b3e8b47a',
    'How do I log in to my account?': 'e318f0ae0c0d',
    "Why can't I sign in?": 'f18c83d9c891',
    'Do I need an account to browse products?': 'd5f6c92f57b5',
    'Where can I update my personal information?': '0800505f8034',
    'How can I save my delivery details?': 'b1496892fc07',
    'Does changing my profile update an existing order address?': '8d8aad619b82',
    'How do I log out?': '4fd04799eb51',
    'Can a customer register as an administrator?': '90c8cc6382ad',
    'How do I search for an electrical product?': '840443a7ea0b',
    'How do I browse products by category?': '7008b5492536',
    'How do I find products within my budget?': 'f32d531fe382',
    'Can I filter by brand?': 'e935fd729e70',
    'Can I sort items by price?': '6988718d30c9',
    'Why is my product search empty?': 'f7dd5831e84b',
    'Where can I read technical specifications?': '8829f0bc1ccd',
    'How can I compare two products?': 'bd78be6e6111',
    'Which currency does Power Pick use?': '35f2a8a12a58',
    'How do I check product availability?': '520b47073c6d',
    'Why did the stock change after I added an item?': '9b95d4acd016',
    'Can I buy an out-of-stock item?': '6551bbfe3a24',
    'Is there a guaranteed restock date?': 'c049aed93545',
    'What should I compare when choosing a wire or cable?': 'a32b886bf214',
    'How do I choose a modular switch?': 'ee4410476197',
    'What should I check on a socket listing?': '96f1c4339f8c',
    'How can I compare MCBs in the catalogue?': '2cafecfc78cc',
    'What does the pole count on a breaker mean?': '99a8aac382f5',
    'What should I compare when choosing an LED lamp?': 'cb6ee91769bd',
    'How do I compare colour temperatures on LED lights?': '232eb4b2a51c',
    'How can I select a screwdriver for an electrical job?': '30ea2d89f9a8',
    'Which pliers should I look for?': '7ce545921595',
    'How do I select a wire stripper?': 'f72cb872fe1c',
    'What should I compare when choosing a multimeter?': '1743619bac45',
    'How can I tell whether a modular board and insert fit together?': '59c56ac4a76d',
    'How do I compare rolls of insulation tape?': '4930ccd094b3',
    'Can product recommendations confirm installation safety?': 'b1916b6a920a',
    'How do I add an item to my cart?': '95ae4a294742',
    'How do I change a cart quantity?': '7c90d2e8f36f',
    'How do I remove a cart item?': '5e253827aea6',
    "Why can't I order the quantity I entered?": '794d1458d9f4',
    'Where do I see my cart total?': '0bcf7e5875fb',
    'How do I place an order?': '59398b424f7b',
    'Which delivery address will the store use?': '242d391910db',
    'What if my cart is empty?': '0cfb9fba6b11',
    "Why is an old order price different from today's listing?": 'f3b83364b9bc',
    'What payment methods does Power Pick accept?': '01b0f4d9d62f',
    'How does Cash on Delivery work?': '5272aa3bc157',
    'Does choosing COD charge my card?': '5fb29c4a321f',
    'How do I pay by card or UPI?': 'ed19d6c9994a',
    'Does Power Pick process real online payments?': 'af7f1fddab93',
    'Where do I enter my payment details?': 'f0843a13af56',
    'What should I do if online payment fails?': 'd2654e6e9818',
    'What happens if I close the Razorpay payment window?': '891b881c1bc2',
    'How can I retry an unpaid online order?': '152f0ba3e0c3',
    'How is an online payment verified?': 'c81f1d7f80e2',
    'Where can I view my payment history?': '9d023612dd18',
    'Why is a confirmed COD order marked unpaid?': 'cb77d766ab4c',
    'What is a payment reference?': '2288e807340c',
    'Does the store save card numbers or UPI credentials?': '351df2346bd7',
    'Where can I find my previous orders?': '5315edac6d44',
    'How do I track my order?': '8b8a1c1fa24c',
    'What is the difference between order status and payment status?': 'f82349eb641a',
    'What does Processing mean?': '2622c8afb5b1',
    'What does Shipped mean?': '2af5dc23c117',
    'What does Delivered mean?': '64b8937a0141',
    "Does tracking show a courier's live location?": '4f461a7224fd',
    'Does the store guarantee a delivery date?': 'abf979fbece8',
    'Can the assistant cancel my order?': 'b7050778be0f',
    'What does Cancelled mean?': 'ddbec719cae5',
    'How can I get help using the store?': '9aa923a2d468',
    'Can the assistant read my personal order details?': '6a0771878c30',
    'Can I ask the assistant for a product recommendation?': 'a5221f97c4f4',
    'What if my question has no published answer?': '42788d699619',
    'Does Power Pick promise a product warranty?': '88745af3b5a2',
    'Does Power Pick offer an automatic refund?': '3cad2b5aa43c',
    'How can I contact a human support agent?': '5eda8ce76357',
    'How do I save my delivery details?': 'dbf3876b361f',
    'Does changing my profile change an order I already placed?': '60e5acb1c656',
    'What are the steps at checkout?': '572e1f209c2b',
    'What delivery details are required?': '7114803c04bf',
    'What happens when I place an order?': 'ea974991ebd6',
    'How do I pay for an order?': '75dac350dd5f',
    'What do the payment statuses mean?': '378c498a03ec',
    'What does Pending mean?': 'a8b215932346',
    'What does Confirmed mean?': '4f600b6ff59a',
    'How do I cancel an order?': 'abbc687d9484',
    'What happens to stock when an order is cancelled?': 'ab25130060c9',
}


def digest(text):
    """Short fingerprint of an answer, to tell a seeded answer from one staff have edited."""
    return hashlib.sha1(text.encode()).hexdigest()[:12]


def read_faqs(path):
    """A second-level heading groups questions. Each third-level heading starts an answer."""
    category = ""
    question = ""
    answer = []
    for line in path.read_text(encoding="utf-8").splitlines() + ["## End"]:
        if line.startswith(("## ", "### ")):
            if question:
                if not category or not any(answer):
                    raise CommandError(f"Missing FAQ category or answer for {question}")
                yield category, question, "\n".join(answer).strip()
            question, answer = "", []
            if line.startswith("### "):
                question = line[4:].strip()
            else:
                category = line[3:].strip()
        elif question:
            answer.append(line.strip())


class Command(BaseCommand):
    help = "Add the demonstration catalogue and FAQs, keeping existing stock, prices and answers."

    @transaction.atomic
    def handle(self, *args, **options):
        assets = settings.BASE_DIR / "store" / "seed_assets"
        catalogue = json.loads((assets / "catalogue.json").read_text(encoding="utf-8"))
        groups = json.loads((assets / "variant_groups.json").read_text(encoding="utf-8"))
        faq_entries = list(read_faqs(settings.BASE_DIR / "knowledge" / "faq_seed.md"))
        added_products = added_faqs = refreshed_faqs = retired_faqs = 0

        # Rotate through families so the first page shows a variety of tools and supplies.
        for variant_number in range(max(len(f["variants"]) for f in catalogue.values())):
            for family_key, family in catalogue.items():
                if variant_number >= len(family["variants"]):
                    continue
                name, brand, price, stock, specs = family["variants"][variant_number]
                category, _ = Category.objects.get_or_create(name=family["category"])
                image_name = f"products/demo/{family_key}.webp"
                if not default_storage.exists(image_name):
                    with (assets / f"{family_key}.webp").open("rb") as source:
                        image_name = default_storage.save(image_name, File(source))

                group, label = groups.get(name, ("", ""))
                # Defaults apply only when creating a row. A rerun must keep staff edits.
                _, created = Product.objects.get_or_create(name=name, defaults={
                    "category": category, "brand": brand, "price": price, "stock": stock,
                    "description": family["description"], "specs": specs, "image": image_name,
                    "variant_group": group, "variant_label": label,
                })
                added_products += created

        for category, question, answer in faq_entries:
            faq, created = FAQ.objects.get_or_create(
                question=question, defaults={"category": category, "answer": answer}
            )
            added_faqs += created
            # Refresh only rows still carrying an earlier seeded answer; staff edits are kept.
            if not created and faq.answer != answer and digest(faq.answer) == LEGACY_ANSWERS.get(question):
                faq.answer, faq.category = answer, category
                faq.save(update_fields=["answer", "category"])
                refreshed_faqs += 1

        # Retire earlier seeded questions that are no longer in the seed (unedited rows only).
        current = {question for _, question, _ in faq_entries}
        for question, old_digest in LEGACY_ANSWERS.items():
            if question not in current:
                for faq in FAQ.objects.filter(question=question):
                    if digest(faq.answer) == old_digest:
                        faq.delete()
                        retired_faqs += 1
        self.stdout.write(self.style.SUCCESS(f"Added {added_products} products and {added_faqs} FAQs; refreshed {refreshed_faqs} and retired {retired_faqs} earlier FAQs."))
