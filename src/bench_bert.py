"""BERT-Base config: memory-heavy transformer forward + backward (random init)."""

from __future__ import annotations

import time

import torch
from transformers import BertConfig, BertModel

from device_util import get_device
from task_common import print_result

STEPS = 30
WARMUP_STEPS = 5
BATCH = 4
SEQ_LEN = 128


def main() -> None:
    device = get_device()
    print(f"Starting BERT-Base (random init) benchmark on {device}...")

    config = BertConfig(
        hidden_size=768,
        num_hidden_layers=12,
        num_attention_heads=12,
        intermediate_size=3072,
        max_position_embeddings=SEQ_LEN,
    )
    model = BertModel(config).to(device)
    model.train()
    opt = torch.optim.AdamW(model.parameters(), lr=1e-4)

    # Pre-generate all token batches once (avoids RNG cost inside the timed loop).
    total_batches = WARMUP_STEPS + STEPS
    all_inp = torch.randint(
        0,
        config.vocab_size,
        (total_batches, BATCH, SEQ_LEN),
        device=device,
    )
    attn = torch.ones(BATCH, SEQ_LEN, device=device)

    # Warmup: CUDA allocator / kernels settle before JCT measurement.
    for i in range(WARMUP_STEPS):
        inp = all_inp[i]
        opt.zero_grad()
        out = model(input_ids=inp, attention_mask=attn)
        loss = out.last_hidden_state.mean()
        loss.backward()
        opt.step()

    if device.type == "cuda":
        torch.cuda.synchronize()

    t0 = time.perf_counter()

    for i in range(STEPS):
        inp = all_inp[WARMUP_STEPS + i]
        opt.zero_grad()
        out = model(input_ids=inp, attention_mask=attn)
        loss = out.last_hidden_state.mean()
        loss.backward()
        opt.step()

    if device.type == "cuda":
        torch.cuda.synchronize()
        torch.cuda.empty_cache()

    duration = time.perf_counter() - t0
    print_result(
        "bert_base",
        duration,
        DEVICE=str(device),
        WARMUP_STEPS=WARMUP_STEPS,
        STEPS=STEPS,
        BATCH=BATCH,
        SEQ_LEN=SEQ_LEN,
        METRIC="final_loss",
        VALUE=f"{loss.item():.6f}",
    )
