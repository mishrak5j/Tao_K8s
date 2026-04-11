"""Single entrypoint: python src/run_task.py --task resnet|bert|yolo|dlrm"""

from __future__ import annotations

import argparse

from bench_bert import main as bert_main
from bench_dlrm import main as dlrm_main
from bench_resnet import main as resnet_main
from bench_yolo import main as yolo_main

TASKS = {
    "resnet": resnet_main,
    "bert": bert_main,
    "yolo": yolo_main,
    "dlrm": dlrm_main,
}


def main() -> None:
    p = argparse.ArgumentParser(description="Tao-K8s GPU benchmark runner")
    p.add_argument(
        "--task",
        required=True,
        choices=sorted(TASKS),
        help="Benchmark task name",
    )
    args = p.parse_args()
    TASKS[args.task]()


if __name__ == "__main__":
    main()
