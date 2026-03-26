FROM docker.shlab.tech/public/python:3.13-slim

RUN sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && apt-get install -y --no-install-recommends \
    curl xz-utils \
    libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 \
    libffi-dev libcairo2 shared-mime-info fonts-wqy-zenhei && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

RUN ARCH=$(dpkg --print-architecture) && \
    if [ "$ARCH" = "amd64" ]; then NARCH="x64"; else NARCH="$ARCH"; fi && \
    curl -fsSL "https://registry.npmmirror.com/-/binary/node/v20.18.0/node-v20.18.0-linux-${NARCH}.tar.xz" \
      | tar -xJ -C /usr/local --strip-components=1 && \
    node --version && npm --version

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn

COPY frontend/package*.json frontend/
RUN cd frontend && npm install --registry https://registry.npmmirror.com

COPY . .

RUN cp -n backend/config.py.example backend/config.py && \
    mkdir -p backend/logs backend/charts backend/downloads backend/reports

EXPOSE 5000

CMD ["python", "-m", "backend.app"]
