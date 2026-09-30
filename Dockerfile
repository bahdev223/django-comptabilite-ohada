FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY . /app

RUN python -m pip install --upgrade pip \
    && pip install --no-cache-dir -e ".[rest]" gunicorn

ENV DJANGO_SETTINGS_MODULE=standalone.settings

RUN python manage.py collectstatic --noinput || true

EXPOSE 8000

CMD ["gunicorn", "standalone.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
