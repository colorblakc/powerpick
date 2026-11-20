# Demo catalogue assets

`catalogue.json` supplies the demonstration product names, sample brands, prices in rupees, stock and specifications. Each variant row contains its name, brand, price, quantity and specification lines in that order. Four sizes or ratings can share one representative product-family photograph.

The local WebP photographs are illustrative product shots made for Power Pick: one centered, unbranded product on a seamless warm-gray studio surface, with soft daylight and a small contact shadow. The subjects are pliers, a multimeter, copper wire, a miniature circuit breaker, a modular rocker switch, a bayonet LED bulb, a surface box, electrical tape, a cordless drill, a three-pin socket, a slotted screwdriver and a reel of LED strip.

Run `python manage.py seed_demo` after migrations. The command copies each product-family image to the configured media storage and creates missing records. Staff can upload individual product photos later.
