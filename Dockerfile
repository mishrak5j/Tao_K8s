# CPU PyTorch image for local Minikube / Mac smoke (benchmarks)
FROM python:3.11-slim
WORKDIR /app

ENV PYTHONPATH=/app/src

# OpenCV (ultralytics) needs these on slim images
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libxcb1 libgomp1 libgl1 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"

COPY src/ ./src/

ENTRYPOINT ["python", "src/run_task.py"]
CMD ["--task", "resnet"]
