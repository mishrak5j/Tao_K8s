"""YOLOv8n: latency-oriented detection (Ultralytics)."""

from __future__ import annotations

import time

import numpy as np
import torch
from ultralytics import YOLO

from device_util import get_device
from task_common import print_result

RUNS = 25
WARMUP_RUNS = 5
MODEL_NAME = "yolov8n.pt"


def main() -> None:
    device = get_device()
    print(f"Starting YOLOv8 ({MODEL_NAME}) benchmark on {device}...")

    yolo_device = 0 if device.type == "cuda" else "cpu"
    model = YOLO(MODEL_NAME)
    h, w = 640, 640
    frame = torch.randint(0, 256, (1, 3, h, w), dtype=torch.float32)
    # Single fixed input for all runs (data prep outside the timed loop).
    arr = frame[0].permute(1, 2, 0).cpu().numpy().astype(np.uint8)

    for _ in range(WARMUP_RUNS):
        model.predict(arr, verbose=False, imgsz=h, device=yolo_device)
        if device.type == "cuda":
            torch.cuda.synchronize()

    t0 = time.perf_counter()
    total_ms = 0.0
    for _ in range(RUNS):
        t_step = time.perf_counter()
        model.predict(arr, verbose=False, imgsz=h, device=yolo_device)
        if device.type == "cuda":
            torch.cuda.synchronize()
        total_ms += (time.perf_counter() - t_step) * 1000

    if device.type == "cuda":
        torch.cuda.empty_cache()

    duration = time.perf_counter() - t0
    avg_ms = total_ms / RUNS
    print_result(
        "yolov8n",
        duration,
        DEVICE=str(device),
        WARMUP_RUNS=WARMUP_RUNS,
        RUNS=RUNS,
        METRIC="avg_latency_ms",
        VALUE=f"{avg_ms:.4f}",
    )
