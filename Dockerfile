# CPU PyTorch image for local Minikube / Mac smoke (benchmarks)
FROM python:3.11-slim
WORKDIR /app

ENV PYTHONPATH=/app/src

RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"

COPY src/ ./src/

ENTRYPOINT ["python", "src/run_task.py"]
CMD ["--task", "resnet"]
