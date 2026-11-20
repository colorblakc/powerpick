"""Update unchanged demonstration answers after cash on delivery was disabled for new orders."""
from django.db import migrations

# Staff-edited answers are deliberately left alone.
ANSWERS = {'Cart, then Delivery, then Payment. You review your items, confirm the delivery address and phone number, and then choose cash on delivery or online payment with Razorpay.': 'Cart, then Delivery, then Payment. Review your items and delivery details, then continue to Razorpay for online payment.', 'The items are held for you. With online payment the order is Pending and you are taken to the payment page; it is confirmed once the payment is verified. With cash on delivery the order is Confirmed straight away and you pay in cash on delivery.': 'The items are held for you. The order is Pending and you are taken to the payment page; it is confirmed once payment is verified.', 'You can pay online through Razorpay, using UPI, cards or netbanking in its secure checkout, or choose cash on delivery and pay in cash when the order arrives.': 'Pay online through Razorpay using the available payment methods. Cash on delivery is currently unavailable for new orders.', "Choose Cash on delivery at checkout. The order is confirmed straight away, its items are held for you and nothing is charged online. You pay the order total in cash when it is delivered, and the order's payment stays Unpaid until staff record the cash as collected.": 'Cash on delivery is currently unavailable for new orders. Existing cash on delivery orders keep their original payment details.', "For online payment, you reach the payment page after you place the order. Choose Pay, then complete the payment in Razorpay's secure checkout with UPI, a card or netbanking. For cash on delivery there is nothing to pay online; keep the order total ready in cash.": "After placing the order, choose Pay on the payment page and complete payment in Razorpay's secure checkout using an available method.", 'Payment has been received and verified, or the order was placed with cash on delivery. Staff have not started preparing the order yet.': 'Payment has been received and verified. Staff have not started preparing the order yet.'}

def update_answers(apps, schema_editor):
    FAQ = apps.get_model("store", "FAQ")
    for old, new in ANSWERS.items():
        FAQ.objects.filter(answer=old).update(answer=new)

class Migration(migrations.Migration):
    dependencies = [("store", "0007_profile_avatar")]
    operations = [migrations.RunPython(update_answers, migrations.RunPython.noop)]
