FROM pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime@sha256:77f17f843507062875ce8be2a6f76aa6aa3df7f9ef1e31d9d7432f4b0f563dee
WORKDIR /app
ENV HF_HUB_DISABLE_XET=1 PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 HF_HOME=/models/huggingface \
    LOCAL_MODEL_CACHE=/models/nllb STUDIO_HOST=0.0.0.0 STUDIO_PORT=8000
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY frontend ./frontend
COPY experiments/*.py experiments/*.json ./experiments/
COPY tests ./tests
COPY diagnose_network.py ./diagnose_network.py
EXPOSE 8000
CMD ["python", "-m", "backend.server"]

