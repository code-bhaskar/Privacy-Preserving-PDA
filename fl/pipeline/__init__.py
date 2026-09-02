"""Single-pipeline federated learning controls.

``supervisor`` lets the one FastAPI app (``app/main.py``) own the whole FL demo:
prepare the SNIPS shards, spawn the independent client processes, drive rounds and
the epsilon sweep, and export the aggregated model to ONNX — without a second
coordinator server or a handful of extra shells.
"""
from fl.pipeline.supervisor import (  # noqa: F401
    dataset_job,
    dataset_status,
    pipeline_status,
    shutdown,
    supervisor,
    sweep_runner,
)
