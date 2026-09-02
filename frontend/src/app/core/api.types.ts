/**
 * Types mirroring the FastAPI pydantic schemas in `app/schemas/*`.
 * Kept in one file so the demo UI stays easy to read top-to-bottom.
 */

export interface User {
  id: number;
  name: string;
  email: string;
  preferences: Record<string, unknown>;
  created_at: string;
}

export interface Token {
  access_token: string;
  token_type: string;
}

export interface Consent {
  id: number;
  user_id: number;
  category: string;
  granted: boolean;
  created_at: string;
}

export type ConsentCategory =
  | 'assistant_nlu'
  | 'calendar_data'
  | 'message_summarization'
  | 'federated_training';

export interface CalendarEvent {
  id: number;
  user_id: number;
  title: string;
  participant: string | null;
  start_time: string;
  end_time: string;
  created_via: string;
}

export interface Reminder {
  id: number;
  user_id: number;
  text: string;
  due_time: string;
  status: string;
}

/**
 * Occlusion-saliency attribution: the drop in predicted probability when the
 * token is hidden. Positive = evidence for the chosen intent.
 */
export interface SaliencyToken {
  token: string;
  contribution: number;
}

export interface CommandExplanation {
  method: string;
  top_tokens: SaliencyToken[];
}

export interface CommandResponse {
  intent: string;
  confidence: number;
  requires_ml: boolean;
  entities: Record<string, unknown>;
  action_taken: string;
  result: unknown;
  processing_location: string;
  explanation: CommandExplanation | null;
}

export interface SummarizeResponse {
  summary: string;
  n_messages: number;
  processing_location: string;
  raw_content_transmitted_externally: boolean;
}

export interface PrivacyPosture {
  technology: string;
  status: string;
  notes: string;
}

export interface EncryptDemoResult {
  algorithm: string;
  ciphertext_b64: string;
  roundtrip_ok: boolean;
}

export interface AuditRecord {
  id: number;
  user_id: number | null;
  action: string;
  data_type: string;
  reason: string;
  external_processing: boolean;
  processing_location: string;
  prev_hash: string | null;
  integrity_hash: string | null;
  created_at: string;
}

export interface AuditVerifyResult {
  valid: boolean;
  total_records: number;
  broken_at_id: number | null;
  message: string;
}

/* ---------------------------- federated learning --------------------------- */

export interface ClientContribution {
  client_id: string;
  n_local_samples: number;
  payload_bytes: number;
  dp_epsilon: number | null;
  masked: boolean;
  raw_data_transmitted: boolean;
}

export interface RoundResult {
  round_id: number;
  n_clients: number;
  dp_epsilon: number | null;
  global_accuracy: number;
  latency_ms: number;
  comm_bytes_total: number;
  model_size_bytes: number;
  contributions: ClientContribution[];
}

export interface PrivacySpent {
  epsilon: number;
  delta: number;
  rounds: number;
  noise_multiplier: number;
  sampling_rate_q?: number;
  optimal_rdp_order?: number;
  note?: string;
}

export interface CoordinatorRound {
  phase: string;
  round_id: number;
  config: Record<string, unknown>;
  peer_pubkeys: Record<string, unknown>;
  survivors: number[];
  dropped: number[];
  registered_clients: number;
  collected: number;
}

export interface HistoryRecord {
  round_id: number;
  round_wall_time_s: number;
  participants: number[];
  survivors: number[];
  dropped: number[];
  dropout_recovered: boolean;
  test_accuracy: number;
  test_loss: number;
  clip_norm: number;
  noise_multiplier: number;
  target_epsilon: number | null;
  privacy_spent: PrivacySpent | null;
  bytes_per_client_uplink: number;
  total_uplink_bytes: number;
  server_saw_plaintext_updates: boolean;
}

export interface DatasetShard {
  client_id: number;
  samples: number;
}

export interface DatasetInfo {
  ready: boolean;
  data_root: string;
  num_classes: number | null;
  intents: string[];
  alpha: number | null;
  planned_clients: number | null;
  test_samples: number;
  shards: DatasetShard[];
  total_train_samples: number;
}

export interface DatasetJobStatus {
  running: boolean;
  exit_code: number | null;
  started_at: number | null;
  finished_at: number | null;
  log: string;
  dataset: DatasetInfo;
}

export interface SupervisedClient {
  client_id: number;
  pid: number;
  alive: boolean;
  exit_code: number | null;
  started_at: number;
  uptime_s: number;
  drop_at: string | null;
  server_url: string;
  log_path: string;
  shard: string;
}

export interface RegisteredClient {
  client_id: number;
  num_samples: number | null;
  last_seen_age_s: number;
}

export interface SweepPoint {
  epsilon: number | null;
  epsilon_label: string;
  final_accuracy: number;
  mean_accuracy: number;
  accuracy_curve: number[];
  final_loss: number | null;
  avg_round_wall_time_s: number | null;
  noise_multiplier: number | null;
  privacy_spent: PrivacySpent | null;
  comm_bytes_per_client: number;
  model_size_bytes: number;
  rounds: number;
}

export interface SweepRoundRow {
  epsilon: number | null;
  epsilon_label: string;
  round: number;
  test_accuracy: number;
  test_loss: number;
  noise_multiplier: number;
  wall_time_s: number;
  survivors: number[];
  dropped: number[];
  total_uplink_bytes: number;
  privacy_spent: PrivacySpent | null;
  server_saw_plaintext_updates: boolean;
}

export interface SweepStatus {
  running: boolean;
  started_at: number | null;
  finished_at: number | null;
  elapsed_s: number | null;
  epsilons: (number | null)[];
  rounds: number;
  clients_per_round: number;
  current_epsilon: number | null;
  current_epsilon_label: string;
  completed_rounds: number;
  total_rounds: number;
  progress_pct: number;
  points: SweepPoint[];
  rounds_log: SweepRoundRow[];
  error: string | null;
}

export interface PipelineStatus {
  single_pipeline: boolean;
  coordinator_in_process: boolean;
  coordinator_url: string;
  server_url: string;
  phases: string[];
  dataset: DatasetInfo;
  dataset_job: DatasetJobStatus;
  clients: SupervisedClient[];
  clients_alive: number;
  registered: { registered_clients: number; clients: RegisteredClient[] };
  /** Registered with the coordinator but started outside the supervisor. */
  registered_not_supervised: number[];
  round: CoordinatorRound;
  model_dim: number;
  model_size_bytes: number;
  sweep: SweepStatus;
  privacy_spent: PrivacySpent | null;
  history: HistoryRecord[];
  history_count: number;
  results_file: string;
  results_file_exists: boolean;
  python_executable: string;
  /** Federated (SNIPS, 7-class) artifact written by the export step. */
  onnx_artifact: string;
  onnx_artifact_exists: boolean;
  /** The artifact `/assistant/command` actually serves (8 assistant intents). */
  live_model_artifact: string;
  live_model_artifact_exists: boolean;
  live_model_classes: number;
  federated_model_classes: number;
  artifacts: {
    accuracy_plot: string;
    metrics_csv: string;
    federated_onnx: string;
    federated_int8: string;
    live_onnx: string;
    benchmark: string;
    model_card: string;
    export_log: string;
  };
}

export interface SpawnResult {
  spawned: SupervisedClient[];
  errors: string[];
  error?: string;
}

export interface ClientLog {
  client_id: number;
  found: boolean;
  alive?: boolean;
  lines: string[];
}

export interface OnnxExportResult {
  ok: boolean;
  log_path: string;
  steps: { module: string; exit_code: number; stdout: string; stderr: string }[];
  /** Which artifact was written: 'federated' (default) or 'live'. */
  target: string;
  artifact: string;
  live_assistant_model_modified: boolean;
  /** Parsed deployed_models/model_card_federated.json */
  sizes: {
    target?: string;
    num_classes?: number;
    served_by_assistant?: boolean;
    onnx_path?: string;
    int8_path?: string;
    pytorch_params?: number;
    onnx_fp32_kb?: number;
    onnx_int8_kb?: number;
    compression_ratio?: number;
    model_card?: string;
  } | null;
  /** Parsed deployed_models/benchmark.json when benchmark=true */
  benchmark: Record<string, any> | null;
  /** Which model `benchmark` timed — the SERVED assistant model, not the export. */
  benchmark_target: string | null;
  /** Plain-language summary of what the export did and did not change. */
  note?: string;
}
