"""ResNet-50: GPU compute / CNN baseline (fixed-step training loop)."""

from __future__ import annotations

import time

import torch
import torch.nn as nn
import torchvision.models as models

from device_util import get_device
from task_common import print_result

STEPS = 40
WARMUP_STEPS = 5
BATCH = 8
IMAGE_SIZE = 224


def main() -> None:
    device = get_device()
    print(f"Starting ResNet-50 benchmark on {device}...")

    model = models.resnet50(weights=None)
    model.fc = nn.Linear(model.fc.in_features, 10)
    model = model.to(device)
    model.train()
    opt = torch.optim.SGD(model.parameters(), lr=0.01, momentum=0.9)

    # Pre-generate all image batches once (no RNG inside the timed loop).
    total_batches = WARMUP_STEPS + STEPS
    all_x = torch.randn(
        total_batches,
        BATCH,
        3,
        IMAGE_SIZE,
        IMAGE_SIZE,
        device=device,
    )

    for i in range(WARMUP_STEPS):
        x = all_x[i]
        opt.zero_grad()
        logits = model(x)
        loss = logits.mean()
        loss.backward()
        opt.step()

    if device.type == "cuda":
        torch.cuda.synchronize()

    t0 = time.perf_counter()

    for i in range(STEPS):
        x = all_x[WARMUP_STEPS + i]
        opt.zero_grad()
        logits = model(x)
        loss = logits.mean()
        loss.backward()
        opt.step()

    if device.type == "cuda":
        torch.cuda.synchronize()
        torch.cuda.empty_cache()

    duration = time.perf_counter() - t0
    print_result(
        "resnet50",
        duration,
        DEVICE=str(device),
        WARMUP_STEPS=WARMUP_STEPS,
        STEPS=STEPS,
        BATCH=BATCH,
        IMAGE_SIZE=IMAGE_SIZE,
        METRIC="final_loss",
        VALUE=f"{loss.item():.6f}",
    )
