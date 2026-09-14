FROM python:3.10-slim-bookworm
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends libopenslide0 libvips42 libgomp1 ca-certificates gcc libc6-dev && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN python -m pip install --upgrade pip && python -m pip install torch==2.11.0 torchvision==0.26.0 --index-url ${TORCH_INDEX_URL} && python -m pip install -r backend/requirements.txt && python -m pip check
COPY backend /app/backend
COPY frontend /app/frontend
COPY version.json CHANGELOG.md /app/
COPY deployment/local/entrypoint.sh /app/entrypoint.sh
RUN mkdir -p /state /data && ln -s /state/.secrets.json /app/backend/.secrets.json && ln -s /data/cell_annotation /app/backend/cell_annotation
WORKDIR /app/backend
EXPOSE 8092
ENTRYPOINT ["/bin/bash", "/app/entrypoint.sh"]
