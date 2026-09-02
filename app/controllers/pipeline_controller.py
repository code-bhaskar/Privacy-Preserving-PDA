from sqlalchemy.orm import Session

from app.schemas.pipeline import (
    ClientsSpawnRequest,
    ClientsStopRequest,
    DatasetPrepareRequest,
    OnnxExportRequest,
    SweepRequest,
)
from app.services.pipeline_service import pipeline_service


class PipelineController:
    def status(self):
        return pipeline_service.status()

    def dataset_status(self):
        return pipeline_service.dataset_status()

    def prepare_dataset(self, db: Session, payload: DatasetPrepareRequest):
        return pipeline_service.prepare_dataset(db, payload.clients, payload.alpha)

    def clients(self):
        return pipeline_service.clients()

    def spawn_clients(self, db: Session, payload: ClientsSpawnRequest):
        return pipeline_service.spawn_clients(
            db, payload.count, payload.start_id, payload.drop_at, payload.rounds)

    def stop_clients(self, db: Session, payload: ClientsStopRequest):
        return pipeline_service.stop_clients(db, payload.client_ids)

    def client_log(self, client_id: int, lines: int):
        return pipeline_service.client_log(client_id, lines)

    def sweep_status(self):
        return pipeline_service.sweep_status()

    def start_sweep(self, db: Session, payload: SweepRequest):
        return pipeline_service.start_sweep(db, payload)

    def export_onnx(self, db: Session, payload: OnnxExportRequest):
        return pipeline_service.export_onnx(db, payload.benchmark)


pipeline_controller = PipelineController()
