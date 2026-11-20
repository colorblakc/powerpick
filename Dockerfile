# Power Pick container image: Django served by gunicorn, static files by WhiteNoise.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Gather the CSS, JavaScript and images once at build time. Debug mode is only used for this step,
# so the build needs no secret key.
RUN DJANGO_DEBUG=true python manage.py collectstatic --noinput

# Settings come from environment variables; the database and uploaded photos live in /data.
VOLUME /data
EXPOSE 8000

CMD ["./docker-entrypoint.sh"]
