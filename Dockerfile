FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .
RUN SECRET_KEY=build-only-key DEBUG=false python manage.py collectstatic --noinput \
    && addgroup --system app && adduser --system --ingroup app app \
    && mkdir -p /app/media && chown -R app:app /app \
    && chmod +x /app/entrypoint.sh

USER app
EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "from urllib.request import Request,urlopen; urlopen(Request('http://127.0.0.1:8000/healthz/',headers={'X-Forwarded-Proto':'https'}),timeout=3)"
