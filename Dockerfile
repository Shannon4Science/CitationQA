FROM python:3.11-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gnupg git \
    libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 \
    libffi-dev libcairo2 shared-mime-info fonts-noto-cjk && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY frontend/package*.json frontend/
RUN cd frontend && npm install

COPY . .

RUN mkdir -p backend/logs backend/charts backend/downloads backend/reports

EXPOSE 5000

CMD ["python", "-m", "backend.app"]
