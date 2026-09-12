FROM python:3.13.12-slim@sha256:f1927c75e81efd1e091dbd64b6c0ecaa5630b38635a3d1c04034ac636e1f94c8
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY shop ./shop
RUN useradd --uid 10001 --create-home shop
USER shop
CMD ["python", "-m", "uvicorn", "shop.api:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
