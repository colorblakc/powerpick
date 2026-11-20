"""Update unchanged demo FAQ answers to reflect the checkout options at that time."""
from django.db import migrations

# Update only unchanged seed answers, preserving answers already edited by staff.
ANSWERS = {'Choose Cash on Delivery or Razorpay test checkout. Razorpay displays the test payment methods available for that checkout.': 'Pay online through Razorpay. The payment window shows the available payment methods. Cash on delivery is currently unavailable.', 'Choose Cash on Delivery and confirm the order. The order is recorded with payment pending collection.': 'Cash on delivery is currently unavailable for new orders. Continue to online payment at checkout.', 'COD does not request a card payment at checkout. Review the order summary for the amount due.': 'Cash on delivery is currently unavailable. New orders use the online payment flow.', 'Choose the online payment option at checkout and follow the available Razorpay test-mode steps. The payment window displays the supported test methods.': 'Continue to payment at checkout and choose an available method in the Razorpay window.', 'Use the Razorpay checkout window for its supported test methods. Never enter payment credentials into the assistant.': 'Enter payment details in the Razorpay window. Never enter payment credentials into the assistant.'}

def update_answers(apps, schema_editor):
    FAQ = apps.get_model("store", "FAQ")
    for old, new in ANSWERS.items():
        FAQ.objects.filter(answer=old).update(answer=new)

class Migration(migrations.Migration):
    dependencies = [("store", "0003_seed_variant_groups")]
    operations = [migrations.RunPython(update_answers, migrations.RunPython.noop)]
