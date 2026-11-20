"""Group known demo sizes while keeping the original product records and order history."""
from django.db import migrations

# Only the known demonstration records receive groups. Existing prices and stock stay intact.
GROUPS = {'Combination Pliers · 180 mm': ['Combination Pliers', '180 mm'], 'Compact Combination Pliers · 150 mm': ['Combination Pliers', '150 mm'], 'Long Handle Combination Pliers · 200 mm': ['Combination Pliers', '200 mm'], 'Heavy Duty Combination Pliers · 220 mm': ['Combination Pliers', '220 mm'], 'Copper House Wire · 1.5 mm²': ['Copper House Wire', '1.5 mm²'], 'Copper House Wire · 1 mm²': ['Copper House Wire', '1 mm²'], 'Copper House Wire · 2.5 mm²': ['Copper House Wire', '2.5 mm²'], 'Copper House Wire · 4 mm²': ['Copper House Wire', '4 mm²'], 'Single Pole MCB · 16 A': ['Single Pole C-curve MCB', '16 A'], 'Single Pole MCB · 10 A': ['Single Pole C-curve MCB', '10 A'], 'One Way Rocker Switch · 6 A': ['One Way Rocker Switch', '6 A'], 'One Way Rocker Switch · 16 A': ['One Way Rocker Switch', '16 A'], 'Two Way Rocker Switch · 6 A': ['Two Way Rocker Switch', '6 A'], 'Two Way Rocker Switch · 16 A': ['Two Way Rocker Switch', '16 A'], 'Modular Surface Box · 2 Module': ['Modular Surface Box', '2 modules'], 'Modular Surface Box · 4 Module': ['Modular Surface Box', '4 modules'], 'Modular Surface Box · 6 Module': ['Modular Surface Box', '6 modules'], 'Modular Surface Box · 8 Module': ['Modular Surface Box', '8 modules'], 'PVC Electrical Tape · 18 mm': ['PVC Electrical Tape', '18 mm × 9 m'], 'Long Roll Electrical Tape · 18 mm': ['PVC Electrical Tape', '18 mm × 18 m'], 'Narrow Electrical Tape · 12 mm': ['PVC Electrical Tape', '12 mm × 9 m'], 'Wide Electrical Tape · 25 mm': ['PVC Electrical Tape', '25 mm × 18 m']}

def group_demo_products(apps, schema_editor):
    Product = apps.get_model("store", "Product")
    for name, (group, label) in GROUPS.items():
        Product.objects.filter(name=name, variant_group="", variant_label="").update(
            variant_group=group, variant_label=label)

class Migration(migrations.Migration):
    dependencies = [("store", "0002_product_variant_group_product_variant_label")]
    operations = [migrations.RunPython(group_demo_products, migrations.RunPython.noop)]
