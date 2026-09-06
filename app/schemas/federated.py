from pydantic import BaseModel, ConfigDict, Field, field_validator


class RoundRequest(BaseModel):
    n_clients: int | None = Field(None, ge=2, le=8)
    rounds: int = Field(1, ge=1, le=50)
    epsilon: float | None = Field(5.0, gt=0.0)     # None => no DP
    secure_aggregation: bool = True


class ClientContribution(BaseModel):
    client_id: str
    n_local_samples: int
    payload_bytes: int
    dp_epsilon: float | None
    masked: bool
    raw_data_transmitted: bool = False


class RoundResult(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    round_id: int
    n_clients: int
    dp_epsilon: float | None
    global_accuracy: float
    latency_ms: float
    comm_bytes_total: int
    model_size_bytes: int
    contributions: list[ClientContribution]


class ExperimentRequest(BaseModel):
    epsilons: list[float | None] = Field(
        default_factory=lambda: [None, 10.0, 5.0, 1.0],
        min_length=1,
        max_length=16,
    )
    rounds: int = Field(5, ge=1, le=50)
    n_clients: int = Field(5, ge=2, le=8)

    @field_validator("epsilons")
    @classmethod
    def validate_epsilons(cls, values: list[float | None]) -> list[float | None]:
        if any(e is not None and e <= 0 for e in values):
            raise ValueError("epsilon values must be positive or null for no DP")
        return values


class ExperimentPoint(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    epsilon: float | None
    epsilon_label: str
    accuracy: float
    avg_round_latency_ms: float
    comm_bytes_per_client: int
    model_size_bytes: int


class ExperimentResult(BaseModel):
    baseline_centralized_accuracy: float
    points: list[ExperimentPoint]
