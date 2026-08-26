from pydantic import BaseModel


class RoundRequest(BaseModel):
    n_clients: int | None = None
    rounds: int = 1
    epsilon: float | None = 5.0     # None => no DP
    secure_aggregation: bool = True


class ClientContribution(BaseModel):
    client_id: str
    n_local_samples: int
    payload_bytes: int
    dp_epsilon: float | None
    masked: bool
    raw_data_transmitted: bool = False


class RoundResult(BaseModel):
    round_id: int
    n_clients: int
    dp_epsilon: float | None
    global_accuracy: float
    latency_ms: float
    comm_bytes_total: int
    model_size_bytes: int
    contributions: list[ClientContribution]


class ExperimentRequest(BaseModel):
    epsilons: list[float | None] = [None, 10.0, 5.0, 1.0]
    rounds: int = 5
    n_clients: int = 5


class ExperimentPoint(BaseModel):
    epsilon: float | None
    epsilon_label: str
    accuracy: float
    avg_round_latency_ms: float
    comm_bytes_per_client: int
    model_size_bytes: int


class ExperimentResult(BaseModel):
    baseline_centralized_accuracy: float
    points: list[ExperimentPoint]
