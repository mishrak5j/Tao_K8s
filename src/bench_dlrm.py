"""Minimal DLRM-style model: embeddings + dense MLP (I/O + embedding stress)."""

from __future__ import annotations

import time

import torch
import torch.nn as nn

from device_util import get_device
from task_common import print_result

STEPS = 50
WARMUP_STEPS = 5
BATCH = 2048
NUM_DENSE = 13
NUM_EMB_TABLES = 26
EMB_DIM = 128


class MiniDLRM(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.emb_tables = nn.ModuleList(
            nn.Embedding(10000, EMB_DIM) for _ in range(NUM_EMB_TABLES)
        )
        self.bot_nn = nn.Sequential(
            nn.Linear(NUM_DENSE, EMB_DIM),
            nn.ReLU(),
            nn.Linear(EMB_DIM, EMB_DIM),
        )
        in_top = EMB_DIM * (NUM_EMB_TABLES + 1)
        self.top_nn = nn.Sequential(
            nn.Linear(in_top, 512),
            nn.ReLU(),
            nn.Linear(512, 256),
            nn.ReLU(),
            nn.Linear(256, 1),
        )

    def forward(self, dense: torch.Tensor, emb_idx: list[torch.Tensor]) -> torch.Tensor:
        bot = self.bot_nn(dense)
        emb_outs = [self.emb_tables[i](emb_idx[i]) for i in range(NUM_EMB_TABLES)]
        z = torch.cat([bot] + emb_outs, dim=1)
        return self.top_nn(z)


def main() -> None:
    device = get_device()
    print(f"Starting mini-DLRM benchmark on {device}...")

    model = MiniDLRM().to(device)
    model.train()
    opt = torch.optim.SGD(model.parameters(), lr=0.01)

    total_batches = WARMUP_STEPS + STEPS
    dense = torch.randn(total_batches, BATCH, NUM_DENSE, device=device)
    emb_idx_tables = [
        torch.randint(0, 10000, (total_batches, BATCH), device=device)
        for _ in range(NUM_EMB_TABLES)
    ]

    for i in range(WARMUP_STEPS):
        d = dense[i]
        emb_idx = [emb_idx_tables[t][i] for t in range(NUM_EMB_TABLES)]
        opt.zero_grad()
        logits = model(d, emb_idx)
        loss = logits.mean()
        loss.backward()
        opt.step()

    if device.type == "cuda":
        torch.cuda.synchronize()

    t0 = time.perf_counter()

    for i in range(STEPS):
        bi = WARMUP_STEPS + i
        d = dense[bi]
        emb_idx = [emb_idx_tables[t][bi] for t in range(NUM_EMB_TABLES)]
        opt.zero_grad()
        logits = model(d, emb_idx)
        loss = logits.mean()
        loss.backward()
        opt.step()

    if device.type == "cuda":
        torch.cuda.synchronize()
        torch.cuda.empty_cache()

    duration = time.perf_counter() - t0
    print_result(
        "dlrm_mini",
        duration,
        DEVICE=str(device),
        WARMUP_STEPS=WARMUP_STEPS,
        STEPS=STEPS,
        BATCH=BATCH,
        METRIC="final_loss",
        VALUE=f"{loss.item():.6f}",
    )
