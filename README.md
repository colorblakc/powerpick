<p align="center">
  <img src="docs/banner.png" alt="Power Pick: electrical supplies, live stock, delivered to your door" width="100%">
</p>

<p align="center">
  <img alt="Midnight ink" src="https://img.shields.io/badge/Ink-0D0B2E-0D0B2E?style=for-the-badge">
  <img alt="Electric violet" src="https://img.shields.io/badge/Violet-5B3DF5-5B3DF5?style=for-the-badge">
  <img alt="Switch mint" src="https://img.shields.io/badge/Mint-2FDDA6-2FDDA6?style=for-the-badge&labelColor=2FDDA6&color=2FDDA6">
  <img alt="Lilac ground" src="https://img.shields.io/badge/Lilac-F6F5FC-F6F5FC?style=for-the-badge&labelColor=F6F5FC&color=F6F5FC">
  <img alt="Warning amber" src="https://img.shields.io/badge/Amber-E8A100-E8A100?style=for-the-badge">
  <img alt="Fault red" src="https://img.shields.io/badge/Red-E0312E-E0312E?style=for-the-badge">
</p>

<p align="center">
  <img alt="Django 4.2" src="https://img.shields.io/badge/Django-4.2_LTS-0C4B33?logo=django&logoColor=white">
  <img alt="Python 3.9+" src="https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white">
  <img alt="SQLite" src="https://img.shields.io/badge/SQLite-003B57?logo=sqlite&logoColor=white">
  <img alt="Razorpay" src="https://img.shields.io/badge/Payments-Razorpay-0C2451">
  <img alt="Groq assistant" src="https://img.shields.io/badge/Assistant-Groq-F55036">
  <img alt="Docker" src="https://img.shields.io/badge/Deploy-Docker-2496ED?logo=docker&logoColor=white">
</p>

# Power Pick

Power Pick is an online store for electrical supplies: wires and cables, MCBs, modular boards, switches and sockets, LED lighting, insulation, tools and testers. Electricians and homeowners compare ratings, pack sizes and live stock, pay online with Razorpay or in cash on delivery, and track their orders. A Groq-powered assistant answers product and order questions. Staff run the catalogue, stock, orders, payments, customers and assistant FAQs from their own workspace.

Built with Django 4.2, SQLite, the Django template language, hand-written CSS and vanilla JavaScript. There is no frontend framework and no build step.

## Contents

- [Features](#features)
- [Run it locally](#run-it-locally)
- [Configuration](#configuration)
- [Deployment](#deployment)
- [Payments and security](#payments-and-security)
- [Project layout](#project-layout)
- [Design](#design)

## Features

**Customers**
- Home page with search, category shortcuts, featured in-stock products and brands.
- Catalogue with search, category, brand, price range, in-stock filter, sorting and pagination. Sizes and ratings of the same product are grouped as options on one listing.
- Product page with photo, specifications, price, live stock, option chips, quantity, add to cart, wishlist, reviews from verified buyers, and related and recently viewed products.
- Cart with live quantity updates and stock warnings. Checkout saves delivery details and re-checks price and stock before anything is reserved.
- Two ways to pay: **Razorpay** (UPI, cards, netbanking) with verified payment, retry and payment history, or **Cash on delivery**.
- Orders with history, status tracking (Pending, Confirmed, Processing, Shipped, Delivered or Cancelled), reorder and printable receipts.
- Accounts with registration, sign-in by username or email, profile, structured Indian delivery address, avatar, password change and wishlist.
- Assistant that greets you, finds products by rating or use, quotes live price and stock, explains ordering and payment, and shows a signed-in customer their own order status.

**Staff** (`/staff/`)
- Overview of orders needing action, payments to review, low stock, revenue and a 14-day order chart.
- Products (add, edit, photo, availability, delete or deactivate), inventory and categories.
- Orders with valid status transitions, a Razorpay payment re-check, and **Mark cash collected** for delivered cash-on-delivery orders.
- Payments list with filters and CSV export, customers (view, edit, deactivate), assistant FAQs, and their own profile and password.

**How payment methods behave**

| | Razorpay | Cash on delivery |
|---|---|---|
| Order starts as | Pending | Confirmed |
| Payment starts as | Unpaid, becomes Paid when verified | Unpaid until staff record the cash |
| Customer can cancel | While Pending and unpaid | While Pending or Confirmed |
| Stock | Reserved at checkout, returned once if cancelled | Same |

## Run it locally

You need Python 3.9 or newer and about 200 MB of disk space. The steps below work on macOS and Linux; Windows notes follow.

```bash
# 1. Get the code and open the project folder
cd PowerPick

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install the dependencies
pip install -r requirements.txt

# 4. Create your settings file, then edit it (see Configuration below)
cp .env.example .env

# 5. Create the database and load the demo shop
python manage.py migrate
python manage.py seed_demo        # 36 products in 8 categories and about 99 assistant FAQs
python manage.py seed_reviews     # optional sample reviews (remove them with --clear)

# 6. Create a staff account
python manage.py create_staff --username admin --email you@example.com

# 7. Start the server
python manage.py runserver
```

Open <http://127.0.0.1:8000/> for the shop and <http://127.0.0.1:8000/staff/> for the staff workspace. Django's data admin is at <http://127.0.0.1:8000/admin/>. All three use the shop's own sign-in, which accepts a username or an email address.

`seed_demo` is safe to run again: it adds missing records, keeps staff edits and refreshes unedited seeded FAQ answers.

**Windows:** create the environment with `py -m venv .venv`, activate it with `.venv\Scripts\activate`, and copy the settings file with `copy .env.example .env`. The other commands are the same.

**What works without keys:** browsing, cart, accounts, cash on delivery and the staff workspace need no keys at all. Without Razorpay keys the online payment page shows a "payments unavailable" message. Without a Groq key the assistant answers from the local FAQ and catalogue.

## Configuration

Settings are read from the environment, or from a `.env` file in the project folder. Never commit `.env`.

| Variable | Purpose |
|---|---|
| `DJANGO_SECRET_KEY` | Long random secret. Required when `DJANGO_DEBUG` is `false`. |
| `DJANGO_DEBUG` | `true` on your computer, `false` on a live site. |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated host names, for example `localhost,127.0.0.1`. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Space-separated origins such as `https://your-app.go.altare.global`. Needed on a live site. |
| `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` | Razorpay API keys (or `RZP_KEY_ID`, `RZP_KEY_SECRET`). The code accepts `rzp_test_` keys only. |
| `RAZORPAY_WEBHOOK_SECRET` | Signing secret for the `/payments/webhook/` endpoint. |
| `GROQ_API_KEY` | Groq key for the assistant (or `GROQ_API`). |
| `GROQ_MODEL` | Optional. Defaults to `openai/gpt-oss-20b` and falls back to `openai/gpt-oss-120b` when rate limited. |
| `DATA_DIR` | Folder for `db.sqlite3` and uploaded photos. Defaults to the project folder; the Docker image uses `/data`. |
| `STAFF_USERNAME`, `STAFF_EMAIL`, `STAFF_PASSWORD` | Optional. `python manage.py ensure_staff` (run on container start) creates this staff account if it is missing. |
| `STORE_CONTACT_NAME`, `STORE_CONTACT_EMAIL`, `STORE_CONTACT_PHONE`, `STORE_CONTACT_ADDRESS` | Optional. Shown on the Contact page. |

Generate a secret key with:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Secret keys never reach the browser.

## Deployment

> **Why a VPS and not a paid platform?** This is a mini-project with a limited scope, so we host it on a VPS-style container host (Altare Docker Apps, free plan) that pulls a Docker image built from this public GitHub repository. In a real-world project we would weigh the options properly and host it on a paid plan of a managed platform, with managed databases, backups, uptime guarantees and a custom domain.

The shop ships as a Docker image. Every push to `main` builds the image on GitHub and publishes it to GitHub's container registry. The host then pulls and runs that image.

```
git push  ->  GitHub Actions builds the image  ->  ghcr.io/OWNER/REPO:latest  ->  host pulls and runs it
```

### 1. Put the code on a public GitHub repository

Create a public repository and push the project to the `main` branch. The workflow in `.github/workflows/docker.yml` runs by itself and publishes the image as `ghcr.io/<owner>/<repo>:latest` (the name is always lower case).

**The repository is public, so it must never contain secrets.** `.env` and `db.sqlite3` are listed in `.gitignore`; keep it that way. All keys are entered later as environment variables on the host. If a key was ever committed, treat it as leaked and create a new one.

### 2. Make the image public

On GitHub open your profile, **Packages**, choose the image, then **Package settings**, and set **Change visibility** to **Public** (new packages can start as private). The host can then pull it without a login.

### 3. Create the app on Altare

In the Altare console open **Apps**, choose **New app**, then **Docker image**, and fill in:

| Field | Value |
|---|---|
| Image | `ghcr.io/<owner>/<repo>:latest` |
| Port | `8000` |
| Data folder | `/data` (this folder is kept when a new image is deployed; the database and uploaded photos live here) |
| Variables | see the table below |

Altare gives the app an HTTPS address such as `https://your-app.go.altare.global`. Open **Settings** and add that exact address to `DJANGO_ALLOWED_HOSTS` (host name only) and `DJANGO_CSRF_TRUSTED_ORIGINS` (with `https://`). Saving the variables restarts the app. The console labels may differ slightly from the ones above.

| Variable | Value |
|---|---|
| `DJANGO_DEBUG` | `false` |
| `DJANGO_SECRET_KEY` | a long random secret (see [Configuration](#configuration)) |
| `DJANGO_ALLOWED_HOSTS` | `your-app.go.altare.global` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://your-app.go.altare.global` |
| `STAFF_USERNAME`, `STAFF_EMAIL`, `STAFF_PASSWORD` | the first staff account, created on start if missing |
| `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET` | optional; Razorpay **test** keys |
| `GROQ_API_KEY`, `GROQ_MODEL` | optional; for the assistant |

Store the API keys and the staff password as **Secrets** if the console offers them; plain variables can be read by anything running in the app.

### 4. What happens on every start

`docker-entrypoint.sh` runs these steps, then starts the web server:

1. Creates `/data/media` if it is missing.
2. `migrate` creates or updates the database tables.
3. `seed_demo` loads the 36 demo products, their photos and the assistant FAQs. It only adds what is missing, so repeating it is safe.
4. `ensure_staff` creates the staff account from the `STAFF_*` variables if it does not exist.

So after any restart, or after deleting and recreating the app, the demo shop and the staff login come back by themselves.

### 5. Connect the Razorpay webhook (optional)

In the Razorpay dashboard (Test Mode) add a webhook for `https://your-app.go.altare.global/payments/webhook/` with the `payment.captured` and `order.paid` events, and use the same value as `RAZORPAY_WEBHOOK_SECRET`. It confirms a payment even if the customer closes the browser early.

### 6. Check that it works

- Open the address, browse the shop and place a cash-on-delivery order.
- Sign in at `/staff/` with the staff account, move the order to Delivered and press **Mark cash collected**.
- If Razorpay keys are set, pay an online order with a test method, then retry a failed one.
- Ask the assistant about a stocked product.

### Updating, and starting again

- **Update:** push to `main`, wait for the **Actions** tab to show the image built, then redeploy the app on Altare (or turn on its automatic image check, which looks for a new image every 15 minutes). The data folder is kept.
- **Start again:** deleting the app and creating it again from the same image gives a fresh shop. Anything created after launch (customers, orders, reviews, uploaded photos) is removed with it; the demo products and the staff account are recreated on start.
- **Run the image on your own computer:**

```bash
docker build -t powerpick .
docker run --rm -p 8000:8000 -v powerpick-data:/data \
  -e DJANGO_DEBUG=true -e STAFF_USERNAME=admin -e STAFF_EMAIL=you@example.com -e STAFF_PASSWORD='choose-a-long-password' \
  powerpick
```

### Troubleshooting

| Problem | What to check |
|---|---|
| Altare cannot pull the image | The package must be public, and the name must be lower case and match exactly. |
| Error 400 or a CSRF error | `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS` must match the app's exact address, with `https://` in the second. |
| App stops at start | Open the app's logs. A missing `DJANGO_SECRET_KEY` is the usual cause when `DJANGO_DEBUG` is `false`. |
| Staff sign-in does not work | The password must pass Django's rules (not too common, at least 8 characters). A rejected password is logged and no account is made. |
| Online checkout unavailable | Check the `rzp_test_` key prefix and secret. |
| Assistant gives only short FAQ answers | Check `GROQ_API_KEY` and `GROQ_MODEL`; the FAQ fallback is used when Groq cannot be reached. |

## Payments and security

- Prices and stock are authoritative on the server, and the price paid is saved on each order line.
- Razorpay orders are created by Django. Signatures are verified on the server, and the amount, currency, order id and ownership are cross-checked with Razorpay's API before an order is marked paid. Processing is idempotent and the webhook is signature-checked.
- Stock is reserved in a transaction at checkout and returned exactly once when an unpaid or cash-on-delivery order is cancelled.
- A payment that arrives after an order was cancelled is recorded and the order moves to **Payment review** so staff can resolve it in the Razorpay dashboard. Cancelling an order is not a gateway refund.
- Staff accounts are created only with `python manage.py create_staff` or `createsuperuser`. Nobody can choose staff rights when registering.
- Razorpay's checkout window shows a "Test Mode" ribbon while test keys are used. Going live needs live keys, removing the `rzp_test_` guard in `store/gateway.py`, and your own legal and payment review.

## Project layout

```
manage.py
requirements.txt
.env.example            copy to .env and fill in
Dockerfile              container image
docker-entrypoint.sh    start-up steps: migrate, seed, staff account, web server
.github/workflows/      builds and publishes the image on every push to main
powerpick/              settings, URLs, WSGI entry point
knowledge/faq_seed.md   assistant knowledge base, loaded by seed_demo
store/
  models.py             Profile, Category, Product, Order, OrderItem, Payment, FAQ, Wishlist, Review
  views.py              home, catalogue, product detail, cart, checkout, wishlist, reviews
  accounts.py           sign-in, registration, profile, orders, receipts, reorder, order cancellation
  gateway.py            Razorpay payment flow and webhook
  staff.py              staff workspace
  chat.py               Groq assistant with retrieval and fallbacks
  pages.py              help pages, robots.txt, error pages
  management/commands/  seed_demo, seed_reviews, create_staff, ensure_staff
  seed_assets/          demo catalogue data and product photos
  templates/            storefront, staff, registration and admin templates
  static/store/         design tokens, page CSS, JavaScript, fonts, brand art, payment logos
docs/banner.png         README banner
```

## Design

The visual identity is "Afterglow": midnight ink `#0D0B2E`, electric violet `#5B3DF5` for actions, switch mint `#2FDDA6` for live and in-stock states, a soft lilac ground `#F6F5FC`, amber for warnings and red for faults. Headings use Bricolage Grotesque and body text uses Figtree, both self-hosted. The electrician mascot appears in the logo and in empty and success states. Colours and spacing live in `store/static/store/tokens.css`, shared components in `ui.css`, and micro-animations in `motion.css` (all switched off for people who prefer reduced motion).
