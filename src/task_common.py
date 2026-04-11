"""Shared helpers for containerized ML training workloads."""


def print_result(task_name: str, duration_sec: float, **metrics: object) -> None:
    """Emit a stable, grep-friendly summary line for experiments and slides."""
    print(f"TASK_NAME={task_name}")
    for key, value in metrics.items():
        print(f"{key}={value}")
    print(f"TOTAL_DURATION_SECONDS={duration_sec:.4f}")
