import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { FlPipelineService } from '../services/fl-pipeline.service';
import { AuthService } from '../services/auth.service';
import { PipelineStatus, PrivacySpent } from '../core/api.types';
import { Pill } from './pill';
import { JsonView } from './json-view';
import { Series, Sparkline } from './sparkline';

const PHASE_META: Record<string, { label: string; icon: string; hint: string }> = {
  IDLE: { label: 'Idle', icon: 'moon', hint: 'No round in flight' },
  ADVERTISE_KEYS: { label: 'Advertise keys', icon: 'key', hint: 'Clients post X25519 public keys' },
  SHARE_KEYS: { label: 'Share keys', icon: 'envelope-lock', hint: 'Shamir (t,n) shares sealed to peers' },
  COLLECT: { label: 'Collect masked', icon: 'inbox', hint: 'Server receives masked uint32 vectors only' },
  UNMASK: { label: 'Unmask', icon: 'unlock', hint: 'Survivors reveal shares; dropout recovery' },
  AGGREGATING: { label: 'Aggregate', icon: 'cpu', hint: 'Masks cancel; global delta applied' },
  DONE: { label: 'Done', icon: 'check2-circle', hint: 'Round complete, accuracy evaluated' },
};

const EPS_PRESETS: { label: string; values: (number | null)[] }[] = [
  { label: '∞ only (fast)', values: [null] },
  { label: '∞, 5', values: [null, 5.0] },
  { label: '∞, 10, 5, 1 (paper sweep)', values: [null, 10.0, 5.0, 1.0] },
];

/**
 * Federated pipeline tab — ONE pipeline.
 *
 * The coordinator runs inside the same FastAPI process as the assistant and audit
 * APIs, and `/federated/pipeline/*` drives the rest of the demo from this page:
 * prepare SNIPS shards, spawn the independent client OS processes, run
 * secure-aggregation rounds, sweep ε and export the aggregated model to ONNX.
 *
 * The client processes stay separate on purpose — that isolation *is* the privacy
 * claim: the server only ever receives masked uint32 vectors and has no code path
 * to an individual update.
 */
@Component({
  selector: 'app-fl-pipeline-panel',
  imports: [FormsModule, Pill, JsonView, Sparkline],
  template: `
    @if (!consentGranted()) {
      <div class="alert alert-warning py-2 small">
        <i class="bi bi-exclamation-triangle-fill me-1"></i>
        Consent category <code>federated_training</code> is not granted —
        <code>POST /federated/round</code> will refuse with <strong>403</strong> until it is.
      </div>
    }
    @if (svc.error(); as err) {
      <div class="alert alert-danger py-2 small">
        <i class="bi bi-exclamation-triangle-fill me-1"></i>{{ err }}
      </div>
    }
    @if (svc.notice(); as note) {
      <div class="alert alert-info py-2 small d-flex justify-content-between align-items-center gap-2">
        <span><i class="bi bi-info-circle-fill me-1"></i>{{ note }}</span>
        <button class="btn btn-sm btn-link p-0" (click)="svc.clearNotice()">dismiss</button>
      </div>
    }

    <!-- ---------------- pipeline overview ---------------- -->
    <div class="card panel mb-3">
      <div class="card-header panel-head">
        <span><i class="bi bi-diagram-3 me-2"></i>Single-pipeline federated learning</span>
        <div class="d-flex gap-2 flex-wrap">
          <app-pill tone="accent" icon="box-seam">1 backend process</app-pill>
          <app-pill [tone]="status()?.registered?.registered_clients ? 'ok' : 'muted'" icon="hdd-network">
            {{ status()?.registered?.registered_clients ?? 0 }} clients registered
          </app-pill>
          <app-pill tone="info" icon="arrow-repeat">polling every 1.5s</app-pill>
        </div>
      </div>
      <div class="card-body">
        <div class="pipeline-flow">
          @for (step of pipelineSteps; track step.title; let i = $index) {
            <div class="flow-step" [class.ready]="step.ready()" [class.pending]="!step.ready()">
              <div class="flow-num">{{ i + 1 }}</div>
              <div class="flow-body">
                <div class="flow-title">{{ step.title }}</div>
                <div class="flow-sub">{{ step.sub() }}</div>
              </div>
              <app-pill [tone]="step.ready() ? 'ok' : 'muted'" [icon]="step.ready() ? 'check-lg' : 'hourglass-split'">
                {{ step.ready() ? 'ready' : 'pending' }}
              </app-pill>
            </div>
            @if (i < pipelineSteps.length - 1) {
              <i class="bi bi-chevron-right flow-arrow"></i>
            }
          }
        </div>

        <!-- phase state machine -->
        <div class="phases mt-3">
          <div class="phases-label">
            Coordinator state machine — round {{ status()?.round?.round_id ?? 0 }}
            <span class="dim">(GET /api/v1/fl/round/status)</span>
          </div>
          <div class="phase-track">
            @for (p of phases(); track p) {
              <div
                class="phase"
                [class.active]="p === currentPhase()"
                [class.past]="isPast(p)"
                [title]="phaseMeta(p).hint"
              >
                <i class="bi" [class]="phaseIcon(p)"></i>
                <span>{{ phaseMeta(p).label }}</span>
              </div>
            }
          </div>
          <div class="phase-detail">
            <span class="dim">collected masked vectors:</span>
            <strong>{{ status()?.round?.collected ?? 0 }}</strong>
            <span class="dim">/ participants:</span>
            <strong>{{ participants().length || (status()?.round?.config?.['num_clients_in_round'] ?? '—') }}</strong>
            <span class="dim ms-3">survivors:</span>
            <strong>{{ (status()?.round?.survivors ?? []).join(', ') || '—' }}</strong>
            <span class="dim ms-3">dropped:</span>
            <strong [class.text-danger]="(status()?.round?.dropped ?? []).length > 0">
              {{ (status()?.round?.dropped ?? []).join(', ') || 'none' }}
            </strong>
          </div>
        </div>
      </div>
    </div>

    <div class="row g-3">
      <!-- ---------------- controls ---------------- -->
      <div class="col-12 col-xl-5">
        <div class="card panel">
          <div class="card-header panel-head">
            <span><i class="bi bi-sliders me-2"></i>Run the pipeline</span>
            @if (svc.busy()) {
              <span class="busy"><span class="spinner-border spinner-border-sm me-2"></span>{{ svc.busyAction() }}</span>
            }
          </div>
          <div class="card-body">
            <!-- step 1: dataset -->
            <div class="step-block">
              <div class="step-title">
                <span class="step-n">1</span>Dataset
                <app-pill [tone]="dataset()?.ready ? 'ok' : 'warn'" [icon]="dataset()?.ready ? 'check-lg' : 'exclamation-triangle'">
                  {{ dataset()?.ready ? 'ready' : 'not prepared' }}
                </app-pill>
              </div>
              @if (dataset(); as d) {
                <div class="dim micro mb-2">
                  {{ d.total_train_samples }} train / {{ d.test_samples }} test utterances ·
                  {{ d.shards.length }} non-IID shards · {{ d.num_classes }} classes ·
                  Dirichlet α={{ d.alpha ?? '—' }}
                </div>
              }
              <div class="d-flex gap-2 align-items-center flex-wrap">
                <label class="form-label mb-0 small dim" for="dsClients">shards</label>
                <input id="dsClients" type="number" min="2" max="8" class="form-control form-control-sm w-auto"
                       [(ngModel)]="dsClients" />
                <label class="form-label mb-0 small dim" for="dsAlpha">α</label>
                <input id="dsAlpha" type="number" step="0.1" min="0.1" class="form-control form-control-sm w-auto"
                       [(ngModel)]="dsAlpha" style="max-width: 5.5rem" />
                <button class="btn btn-sm btn-outline-primary ms-auto"
                        (click)="prepareDataset()"
                        [disabled]="svc.busy() || datasetJob()?.running === true">
                  <i class="bi bi-cloud-download me-1"></i>Prepare SNIPS
                </button>
              </div>
              @if (datasetJob()?.running) {
                <div class="micro mt-2">
                  <span class="spinner-border spinner-border-sm me-2"></span>
                  downloading + partitioning in the background… (clones the SONOS nlu-benchmark repo)
                </div>
              }
              @if (dataset(); as d) {
                <div class="shard-bars mt-2">
                  @for (s of d.shards; track s.client_id) {
                    <span class="shard" [title]="'client_' + s.client_id + ': ' + s.samples + ' samples'">
                      c{{ s.client_id }} <b>{{ s.samples }}</b>
                    </span>
                  }
                </div>
              }
            </div>

            <!-- step 2: clients -->
            <div class="step-block">
              <div class="step-title">
                <span class="step-n">2</span>Client processes
                <app-pill [tone]="(status()?.clients_alive ?? 0) > 0 ? 'ok' : 'warn'" icon="hdd-stack">
                  {{ status()?.clients_alive ?? 0 }} alive
                </app-pill>
              </div>
              <p class="dim micro mb-2">
                Independent OS processes spawned <em>by this same API</em>. Each holds its own shard;
                only masked vectors cross the wire.
              </p>

              @if (unsupervised().length) {
                <div class="notice-warn micro mb-2">
                  <i class="bi bi-exclamation-triangle me-1"></i>
                  {{ unsupervised().length }} client(s) are registered with the coordinator but were
                  started outside this panel (ids {{ unsupervised().join(', ') }}). They do take part
                  in rounds — but <em>Stop</em> and <em>Logs</em> cannot manage them, which is why
                  the alive count above can be lower than the registered count.
                </div>
              }
              <div class="d-flex gap-2 align-items-center flex-wrap mb-2">
                <label class="form-label mb-0 small dim" for="clientCount">count</label>
                <input id="clientCount" type="number" min="1" max="8" class="form-control form-control-sm w-auto"
                       [(ngModel)]="clientCount" />
                <div class="form-check mb-0">
                  <input class="form-check-input" type="checkbox" id="dropAt" [(ngModel)]="dropAt" />
                  <label class="form-check-label small dim" for="dropAt">simulate dropout</label>
                </div>
                <button class="btn btn-sm btn-outline-success ms-auto" (click)="spawn()" [disabled]="svc.busy()">
                  <i class="bi bi-play-fill me-1"></i>Spawn
                </button>
                <button class="btn btn-sm btn-outline-danger" (click)="stopAll()" [disabled]="svc.busy() || !(status()?.clients_alive)">
                  <i class="bi bi-stop-fill me-1"></i>Stop all
                </button>
              </div>

              @if (clients().length) {
                <div class="client-list">
                  @for (c of clients(); track c.client_id) {
                    <div class="client">
                      <span class="cid">client_{{ c.client_id }}</span>
                      <span class="dim mono">pid {{ c.pid }}</span>
                      <app-pill [tone]="c.alive ? 'ok' : 'bad'" [icon]="c.alive ? 'heart-pulse' : 'x-circle'">
                        {{ c.alive ? 'alive' : 'exited ' + c.exit_code }}
                      </app-pill>
                      <span class="dim mono">{{ samplesFor(c.client_id) }}</span>
                      <span class="dim mono ms-auto">{{ c.uptime_s }}s</span>
                      <button class="btn btn-sm btn-outline-secondary py-0 px-1"
                              (click)="toggleLog(c.client_id)"
                              [title]="c.log_path">
                        <i class="bi" [class.bi-terminal]="!logOpen(c.client_id)" [class.bi-terminal-fill]="logOpen(c.client_id)"></i>
                      </button>
                      <button class="btn btn-sm btn-outline-danger py-0 px-1" (click)="stopOne(c.client_id)">
                        <i class="bi bi-stop-fill"></i>
                      </button>
                    </div>
                    @if (logOpen(c.client_id)) {
                      <pre class="client-log">@for (l of logLines(c.client_id); track l) {
{{ l }}
}</pre>
                    }
                  }
                </div>
              } @else {
                <p class="muted small mb-0">No supervised client processes yet.</p>
              }
            </div>

            <!-- step 3: round -->
            <div class="step-block">
              <div class="step-title">
                <span class="step-n">3</span>Secure-aggregation round
                <app-pill tone="accent" icon="shield-lock">Bonawitz CCS'17</app-pill>
              </div>
              <div class="d-flex gap-2 align-items-center flex-wrap">
                <label class="form-label mb-0 small dim" for="rndClients">clients</label>
                <input id="rndClients" type="number" min="2" max="8" class="form-control form-control-sm w-auto"
                       [(ngModel)]="roundClients" />
                <label class="form-label mb-0 small dim" for="rndRounds">rounds</label>
                <input id="rndRounds" type="number" min="1" max="10" class="form-control form-control-sm w-auto"
                       [(ngModel)]="roundCount" />
                <label class="form-label mb-0 small dim" for="rndEps">ε</label>
                <select id="rndEps" class="form-select form-select-sm w-auto" [(ngModel)]="roundEpsilon">
                  <option [ngValue]="null">∞ (no DP)</option>
                  <option [ngValue]="10">10</option>
                  <option [ngValue]="5">5</option>
                  <option [ngValue]="1">1</option>
                </select>
                <button class="btn btn-sm btn-primary ms-auto" (click)="runRound()" [disabled]="svc.busy()">
                  <i class="bi bi-lightning-charge-fill me-1"></i>Run round
                </button>
              </div>
              <p class="dim micro mt-2 mb-0">
                Honest refusal by design: with fewer connected clients than requested this returns
                <strong>HTTP 400</strong> with instructions — it never fabricates a result.
              </p>
            </div>

            <!-- step 4: sweep -->
            <div class="step-block">
              <div class="step-title">
                <span class="step-n">4</span>Privacy–utility sweep
                @if (sweep()?.running) {
                  <app-pill tone="info" icon="arrow-repeat">running</app-pill>
                }
              </div>
              <div class="d-flex gap-2 align-items-center flex-wrap mb-2">
                @for (preset of epsPresets; track preset.label) {
                  <button type="button" class="chip" [class.active]="epsPreset() === preset.label"
                          (click)="selectPreset(preset)">
                    {{ preset.label }}
                  </button>
                }
              </div>
              <div class="d-flex gap-2 align-items-center flex-wrap">
                <label class="form-label mb-0 small dim" for="swRounds">rounds/ε</label>
                <input id="swRounds" type="number" min="1" max="20" class="form-control form-control-sm w-auto"
                       [(ngModel)]="sweepRounds" />
                <label class="form-label mb-0 small dim" for="swClients">clients</label>
                <input id="swClients" type="number" min="2" max="8" class="form-control form-control-sm w-auto"
                       [(ngModel)]="sweepClients" />
                <label class="form-label mb-0 small dim" for="swEpochs">epochs</label>
                <input id="swEpochs" type="number" min="1" max="5" class="form-control form-control-sm w-auto"
                       [(ngModel)]="sweepEpochs" style="max-width: 4.5rem" />
                <button class="btn btn-sm btn-outline-primary ms-auto" (click)="startSweep()" [disabled]="svc.busy() || sweep()?.running === true">
                  <i class="bi bi-graph-up-arrow me-1"></i>Start sweep
                </button>
              </div>
              @if (sweep(); as s) {
                @if (s.running || s.total_rounds > 0) {
                  <div class="mt-3">
                    <div class="d-flex justify-content-between micro dim mb-1">
                      <span>{{ s.current_epsilon_label || (s.running ? 'starting…' : 'finished') }}</span>
                      <span>{{ s.completed_rounds }}/{{ s.total_rounds }} rounds · {{ s.progress_pct }}%
                        @if (s.elapsed_s !== null) { · {{ s.elapsed_s }}s }</span>
                    </div>
                    <div class="progress sweep-bar" role="progressbar"
                         [attr.aria-valuenow]="s.progress_pct" aria-valuemin="0" aria-valuemax="100">
                      <div class="progress-bar" [class.running]="s.running" [style.width.%]="s.progress_pct"></div>
                    </div>
                    @if (s.error) {
                      <div class="alert alert-danger py-1 px-2 micro mt-2 mb-0">{{ s.error }}</div>
                    }
                  </div>
                }
              }
            </div>

            <!-- step 5: export -->
            <div class="step-block">
              <div class="step-title">
                <span class="step-n">5</span>Export the aggregated model
                <app-pill [tone]="status()?.onnx_artifact_exists ? 'ok' : 'muted'" icon="file-binary">
                  {{ status()?.onnx_artifact ?? 'intent_model_federated.onnx' }}
                </app-pill>
              </div>
              <div class="d-flex gap-2 align-items-center flex-wrap">
                <button class="btn btn-sm btn-outline-success" (click)="exportOnnx()" [disabled]="svc.busy()">
                  <i class="bi bi-box-arrow-up me-1"></i>Export to ONNX + benchmark
                </button>
                @if (exportSizes(); as sizes) {
                  <span class="dim micro">
                    fp32 {{ sizes.fp32 }} KB · int8 {{ sizes.int8 }} KB · ratio {{ sizes.ratio }}×
                    · {{ sizes.classes }} classes
                  </span>
                }
              </div>

              <div class="row g-2 mt-2">
                <div class="col-12 col-md-6">
                  <div class="mini-card">
                    <div class="dim micro">Federated artifact (this export)</div>
                    <code class="micro">{{ status()?.onnx_artifact }}</code>
                    <div class="micro">
                      {{ status()?.federated_model_classes }} classes · SNIPS intent
                      taxonomy
                    </div>
                  </div>
                </div>
                <div class="col-12 col-md-6">
                  <div class="mini-card">
                    <div class="dim micro">Served by <code>/assistant/command</code></div>
                    <code class="micro">{{ status()?.live_model_artifact }}</code>
                    <div class="micro">
                      {{ status()?.live_model_classes }} classes · assistant intent
                      taxonomy
                      <app-pill
                        [tone]="status()?.live_model_artifact_exists ? 'ok' : 'warn'"
                        icon="shield-check"
                      >
                        {{ status()?.live_model_artifact_exists ? 'loaded' : 'missing' }}
                      </app-pill>
                    </div>
                  </div>
                </div>
              </div>

              @if (svc.exportResult(); as res) {
                <div class="export-result mt-2">
                  <div class="d-flex align-items-center gap-2 flex-wrap">
                    <app-pill
                      [tone]="res.ok ? 'ok' : 'bad'"
                      [icon]="res.ok ? 'check2-circle' : 'x-octagon'"
                    >
                      {{ res.ok ? 'export succeeded' : 'export failed' }}
                    </app-pill>
                    @if (res.live_assistant_model_modified === false) {
                      <app-pill tone="info" icon="shield-lock">served model untouched</app-pill>
                    }
                    <code class="micro">{{ res.artifact }}</code>
                  </div>
                  @if (res.note; as note) {
                    <p class="dim micro mt-2 mb-0">{{ note }}</p>
                  }
                  @if (res.benchmark; as bm) {
                    <div class="micro mt-2">
                      <span class="dim">on-device latency</span>
                      p50 {{ bm['p50_ms'] }} ms · p95 {{ bm['p95_ms'] }} ms ·
                      p99 {{ bm['p99_ms'] }} ms
                      <span class="dim">over {{ bm['samples'] }} inferences of</span>
                      <code>{{ res.benchmark_target }}</code>
                    </div>
                  }
                  <div class="micro dim mt-1">
                    log <code>{{ res.log_path }}</code>
                  </div>
                </div>
              }

              <p class="dim micro mt-2 mb-0">
                Export writes a <strong>separate</strong> artifact and never overwrites the model
                the assistant serves: federated training runs on SNIPS
                ({{ status()?.federated_model_classes }} intents) while
                <code>/assistant/command</code> labels against
                {{ status()?.live_model_classes }} assistant intents. Swapping them would make the
                assistant return confidently wrong intent names, so the loader rejects any ONNX
                model whose output width disagrees with its label list and falls back to the
                TF-IDF classifier instead. <code>--target live</code> performs the swap only when
                the class counts match.
              </p>
            </div>
          </div>
        </div>
      </div>

      <!-- ---------------- results ---------------- -->
      <div class="col-12 col-xl-7">
        <div class="card panel">
          <div class="card-header panel-head">
            <span><i class="bi bi-graph-up me-2"></i>Accuracy vs privacy budget ε</span>
            <app-pill tone="info" icon="eye-slash">lower ε = more privacy, less utility</app-pill>
          </div>
          <div class="card-body">
            @if (sweepSeries().length) {
              <app-sparkline
                [series]="sweepSeries()"
                [labels]="sweepLabels()"
                [height]="240"
                [yMax]="1"
                [valueFormat]="pctFormat"
                ariaLabel="accuracy versus epsilon"
              />
            } @else {
              <app-sparkline [series]="[]" [height]="240" />
            }

            @if (sweepPoints().length) {
              <div class="table-responsive mt-3">
                <table class="table table-sm align-middle data">
                  <thead>
                    <tr>
                      <th>ε target</th>
                      <th>noise σ</th>
                      <th>final acc</th>
                      <th>mean acc</th>
                      <th>ε spent (RDP)</th>
                      <th>δ</th>
                      <th>uplink/client</th>
                      <th>round time</th>
                    </tr>
                  </thead>
                  <tbody>
                    @for (p of sweepPoints(); track p.epsilon_label) {
                      <tr>
                        <td class="eps">{{ p.epsilon_label }}</td>
                        <td class="mono">{{ p.noise_multiplier?.toFixed(3) ?? '0.000' }}</td>
                        <td><strong [class.good]="p.final_accuracy > 0.6" [class.poor]="p.final_accuracy < 0.3">
                          {{ (p.final_accuracy * 100).toFixed(2) }}%</strong></td>
                        <td class="mono dim">{{ (p.mean_accuracy * 100).toFixed(2) }}%</td>
                        <td class="mono">{{ spentEpsilon(p.privacy_spent) }}</td>
                        <td class="mono dim">{{ p.privacy_spent?.delta ?? '—' }}</td>
                        <td class="mono dim">{{ kb(p.comm_bytes_per_client) }}</td>
                        <td class="mono dim">{{ p.avg_round_wall_time_s ?? '—' }}s</td>
                      </tr>
                    }
                  </tbody>
                </table>
              </div>
              <p class="micro dim mt-2 mb-0">
                Accuracy is monotone in ε — the privacy–utility trade-off is
                <em>measured</em>, not asserted. At small ε the model approaches chance (1/7 = 14.3%).
                Written to <code>{{ status()?.results_file }}</code>.
              </p>
            }
          </div>
        </div>

        <div class="card panel mt-3">
          <div class="card-header panel-head">
            <span><i class="bi bi-clock-history me-2"></i>Round history</span>
            <div class="d-flex gap-2">
              <app-pill tone="ok" icon="shield-check">
                server saw plaintext updates: never
              </app-pill>
              <app-pill tone="info" icon="hash">{{ status()?.history_count ?? 0 }} rounds</app-pill>
            </div>
          </div>
          <div class="card-body">
            <div class="table-responsive history-table">
              <table class="table table-sm align-middle data">
                <thead>
                  <tr>
                    <th>Round</th>
                    <th>ε target</th>
                    <th>σ</th>
                    <th>accuracy</th>
                    <th>survivors</th>
                    <th>dropped</th>
                    <th>uplink</th>
                    <th>wall</th>
                    <th>plaintext seen</th>
                  </tr>
                </thead>
                <tbody>
                  @for (h of history(); track h.round_id) {
                    <tr>
                      <td class="mono">{{ h.round_id }}</td>
                      <td>{{ h.target_epsilon === null ? '∞' : h.target_epsilon }}</td>
                      <td class="mono dim">{{ h.noise_multiplier.toFixed(3) }}</td>
                      <td><strong [class.good]="h.test_accuracy > 0.6" [class.poor]="h.test_accuracy < 0.3">
                        {{ (h.test_accuracy * 100).toFixed(2) }}%</strong></td>
                      <td class="mono small">{{ h.survivors.join(', ') }}</td>
                      <td class="mono small" [class.text-warning]="h.dropped.length > 0">
                        {{ h.dropped.length ? h.dropped.join(', ') : '—' }}
                        @if (h.dropout_recovered) { <app-pill tone="accent" icon="arrow-repeat">recovered</app-pill> }
                      </td>
                      <td class="mono dim small">{{ kb(h.total_uplink_bytes) }}</td>
                      <td class="mono dim small">{{ h.round_wall_time_s }}s</td>
                      <td>
                        <app-pill [tone]="h.server_saw_plaintext_updates ? 'bad' : 'ok'"
                                  [icon]="h.server_saw_plaintext_updates ? 'exclamation-triangle' : 'eye-slash'">
                          {{ h.server_saw_plaintext_updates ? 'YES' : 'no' }}
                        </app-pill>
                      </td>
                    </tr>
                  } @empty {
                    <tr><td colspan="9" class="muted small py-3 text-center">
                      No rounds yet — spawn clients and run one.
                    </td></tr>
                  }
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div class="row g-3 mt-0">
          <div class="col-12 col-lg-6">
            <div class="card panel">
              <div class="card-header panel-head">
                <span><i class="bi bi-piggy-bank me-2"></i>Privacy budget spent</span>
              </div>
              <div class="card-body">
                @if (spent(); as s) {
                  <div class="kv">
                    <div class="kv-row"><span class="k">ε (epsilon)</span><span class="v">{{ s.epsilon }}</span></div>
                    <div class="kv-row"><span class="k">δ (delta)</span><span class="v">{{ s.delta }}</span></div>
                    <div class="kv-row"><span class="k">rounds</span><span class="v">{{ s.rounds }}</span></div>
                    <div class="kv-row"><span class="k">noise σ</span><span class="v">{{ s.noise_multiplier }}</span></div>
                    @if (s.sampling_rate_q !== undefined) {
                      <div class="kv-row"><span class="k">sampling q</span><span class="v">{{ s.sampling_rate_q }}</span></div>
                    }
                    @if (s.optimal_rdp_order !== undefined) {
                      <div class="kv-row"><span class="k">RDP order α</span><span class="v">{{ s.optimal_rdp_order }}</span></div>
                    }
                    @if (s.note) {
                      <div class="kv-row"><span class="k">note</span><span class="v dim">{{ s.note }}</span></div>
                    }
                  </div>
                  <p class="micro dim mt-2 mb-0">
                    Rényi DP accounting over the composed rounds — the real (ε, δ) bound, not the target.
                  </p>
                } @else {
                  <p class="muted small mb-0">No DP noise applied yet (ε = ∞ rounds spend nothing).</p>
                }
              </div>
            </div>
          </div>
          <div class="col-12 col-lg-6">
            <div class="card panel">
              <div class="card-header panel-head">
                <span><i class="bi bi-braces me-2"></i>Latest round payload</span>
              </div>
              <div class="card-body">
                @if (svc.roundResults()[0]; as r) {
                  <app-json-view [data]="r" label="POST /api/v1/federated/round → 200" [maxRows]="18" />
                } @else {
                  <p class="muted small mb-0">
                    Run a round to see the raw response — note
                    <code>raw_data_transmitted: false</code> and <code>masked: true</code> per client.
                  </p>
                }
              </div>
            </div>
          </div>
        </div>

        <div class="card panel mt-3">
          <div class="card-header panel-head">
            <span><i class="bi bi-megaphone me-2"></i>What to say about this (honest limits)</span>
          </div>
          <div class="card-body">
            <ul class="limits mb-0">
              <li>
                <strong>One pipeline, still isolated clients.</strong> The coordinator lives in the same
                FastAPI app as the assistant/audit APIs and this tab spawns, monitors and stops the
                client processes — but each client remains a separate OS process that never shares
                memory with the server. Collapsing the <em>ops</em> into one pipeline does not collapse
                the trust boundary.
              </li>
              <li>
                <strong>Secure aggregation is Bonawitz et al. CCS'17</strong> (X25519 ECDH, ChaCha20 PRG
                masking mod 2³², Shamir (t,n) dropout recovery). It defends against an
                <em>honest-but-curious</em> server — not a malicious server that could sybil, and not
                malicious clients (no poisoning robustness).
              </li>
              <li>
                <strong>DP is real and client-level</strong>, but with only a handful of clients there is
                little subsampling amplification: at ε = 1 the model sits near chance. The defensible
                claim is “the trade-off is measured”, not “DP is free”.
              </li>
              <li>
                <strong>The crypto is hand-rolled research-grade</strong> and has not had a third-party
                audit. Do not present it as production-hardened.
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  `,
  styles: [
    `
      .panel {
        background: rgba(13, 21, 36, 0.86);
        border: 1px solid rgba(148, 163, 184, 0.16);
        border-radius: 0.75rem;
      }
      .panel-head {
        background: rgba(9, 14, 25, 0.7);
        border-bottom: 1px solid rgba(148, 163, 184, 0.14);
        color: #e2e8f0;
        font-size: 0.88rem;
        font-weight: 600;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.5rem;
        flex-wrap: wrap;
      }
      .busy {
        font-size: 0.74rem;
        color: #7dd3fc;
        display: inline-flex;
        align-items: center;
      }
      .pipeline-flow {
        display: flex;
        align-items: stretch;
        gap: 0.35rem;
        overflow-x: auto;
        padding-bottom: 0.25rem;
      }
      .flow-step {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        border-radius: 0.6rem;
        padding: 0.45rem 0.7rem;
        border: 1px solid rgba(148, 163, 184, 0.18);
        background: rgba(7, 11, 20, 0.6);
        min-width: 12rem;
        flex: 1 1 auto;
      }
      .flow-step.ready {
        border-color: rgba(34, 197, 94, 0.35);
        background: rgba(34, 197, 94, 0.07);
      }
      .flow-num {
        width: 1.5rem;
        height: 1.5rem;
        border-radius: 50%;
        display: grid;
        place-items: center;
        font-size: 0.72rem;
        font-weight: 700;
        background: rgba(148, 163, 184, 0.18);
        color: #cbd5e1;
        flex: 0 0 auto;
      }
      .flow-step.ready .flow-num {
        background: rgba(34, 197, 94, 0.25);
        color: #86efac;
      }
      .flow-body {
        min-width: 0;
        flex: 1 1 auto;
      }
      .flow-title {
        font-size: 0.8rem;
        font-weight: 600;
        color: #e2e8f0;
      }
      .flow-sub {
        font-size: 0.68rem;
        color: #7c8aa0;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .flow-arrow {
        align-self: center;
        color: #475569;
        flex: 0 0 auto;
      }
      .phases {
        border-top: 1px solid rgba(148, 163, 184, 0.14);
        padding-top: 0.85rem;
      }
      .phases-label {
        font-size: 0.76rem;
        color: #94a3b8;
        margin-bottom: 0.5rem;
        font-weight: 600;
      }
      .phase-track {
        display: flex;
        gap: 0.3rem;
        flex-wrap: wrap;
      }
      .phase {
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        padding: 0.3rem 0.6rem;
        border-radius: 999px;
        font-size: 0.72rem;
        border: 1px solid rgba(148, 163, 184, 0.16);
        color: #64748b;
        background: rgba(7, 11, 20, 0.5);
        transition: all 0.2s ease;
      }
      .phase.past {
        color: #94a3b8;
        border-color: rgba(148, 163, 184, 0.25);
      }
      .phase.active {
        color: #fff;
        background: linear-gradient(120deg, rgba(79, 140, 255, 0.85), rgba(139, 92, 246, 0.85));
        border-color: rgba(147, 197, 253, 0.6);
        box-shadow: 0 0 0 3px rgba(79, 140, 255, 0.18);
      }
      .phase-detail {
        margin-top: 0.6rem;
        font-size: 0.75rem;
        color: #cbd5e1;
        display: flex;
        gap: 0.35rem;
        flex-wrap: wrap;
        align-items: center;
      }
      .step-block {
        border: 1px solid rgba(148, 163, 184, 0.14);
        border-radius: 0.6rem;
        padding: 0.7rem 0.8rem;
        margin-bottom: 0.7rem;
        background: rgba(7, 11, 20, 0.45);
      }
      .step-title {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        font-size: 0.84rem;
        font-weight: 600;
        color: #e2e8f0;
        margin-bottom: 0.45rem;
        flex-wrap: wrap;
      }
      .step-n {
        width: 1.35rem;
        height: 1.35rem;
        border-radius: 50%;
        display: grid;
        place-items: center;
        font-size: 0.7rem;
        background: rgba(79, 140, 255, 0.22);
        color: #bfdbfe;
        flex: 0 0 auto;
      }
      .shard-bars {
        display: flex;
        gap: 0.3rem;
        flex-wrap: wrap;
      }
      .shard {
        font-size: 0.68rem;
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
        color: #94a3b8;
        background: rgba(79, 140, 255, 0.1);
        border: 1px solid rgba(79, 140, 255, 0.22);
        border-radius: 0.35rem;
        padding: 0.1rem 0.4rem;
      }
      .shard b {
        color: #bfdbfe;
      }
      .client-list {
        display: flex;
        flex-direction: column;
        gap: 0.3rem;
      }
      .client {
        display: flex;
        align-items: center;
        gap: 0.45rem;
        font-size: 0.74rem;
        background: rgba(7, 11, 20, 0.7);
        border: 1px solid rgba(148, 163, 184, 0.14);
        border-radius: 0.45rem;
        padding: 0.3rem 0.5rem;
        flex-wrap: wrap;
      }
      .client .cid {
        color: #e2e8f0;
        font-weight: 600;
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      }
      .client-log {
        background: #05080f;
        border: 1px solid rgba(148, 163, 184, 0.16);
        border-radius: 0.45rem;
        padding: 0.5rem 0.6rem;
        margin: 0;
        color: #a5f3fc;
        font-size: 0.68rem;
        line-height: 1.45;
        max-height: 13rem;
        overflow: auto;
        white-space: pre-wrap;
        word-break: break-word;
      }
      .chip {
        background: rgba(79, 140, 255, 0.08);
        border: 1px solid rgba(79, 140, 255, 0.25);
        color: #cbd5e1;
        border-radius: 999px;
        padding: 0.2rem 0.6rem;
        font-size: 0.72rem;
      }
      .chip.active {
        background: rgba(79, 140, 255, 0.3);
        border-color: rgba(147, 197, 253, 0.6);
        color: #fff;
      }
      .sweep-bar {
        height: 8px;
        background: rgba(148, 163, 184, 0.15);
      }
      .sweep-bar .progress-bar {
        background: linear-gradient(90deg, #4f8cff, #a855f7);
        transition: width 0.4s ease;
      }
      .sweep-bar .progress-bar.running {
        background-image: linear-gradient(
          45deg,
          rgba(255, 255, 255, 0.18) 25%,
          transparent 25%,
          transparent 50%,
          rgba(255, 255, 255, 0.18) 50%,
          rgba(255, 255, 255, 0.18) 75%,
          transparent 75%,
          transparent
        );
        background-size: 1rem 1rem;
        animation: stripes 0.8s linear infinite;
      }
      @keyframes stripes {
        from { background-position: 0 0; }
        to { background-position: 1rem 0; }
      }
      table.data {
        color: #cbd5e1;
        font-size: 0.78rem;
        margin-bottom: 0;
      }
      table.data thead th {
        color: #7c8aa0;
        font-size: 0.66rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        border-bottom: 1px solid rgba(148, 163, 184, 0.18);
      }
      table.data td {
        border-bottom: 1px solid rgba(148, 163, 184, 0.08);
      }
      .eps {
        color: #93c5fd;
        font-weight: 600;
      }
      .good {
        color: #4ade80;
      }
      .poor {
        color: #f87171;
      }
      .history-table {
        max-height: 20rem;
        overflow: auto;
      }
      .kv {
        border: 1px solid rgba(148, 163, 184, 0.16);
        border-radius: 0.5rem;
        overflow: hidden;
      }
      .kv-row {
        display: flex;
        justify-content: space-between;
        gap: 1rem;
        padding: 0.28rem 0.6rem;
        font-size: 0.77rem;
        border-bottom: 1px solid rgba(148, 163, 184, 0.1);
      }
      .kv-row:last-child {
        border-bottom: 0;
      }
      .kv-row .k {
        color: #7dd3fc;
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      }
      .kv-row .v {
        color: #e2e8f0;
      }
      .limits {
        color: #94a3b8;
        font-size: 0.78rem;
        line-height: 1.6;
        padding-left: 1.1rem;
        margin: 0;
      }
      .limits li {
        margin-bottom: 0.4rem;
      }
      .limits strong {
        color: #e2e8f0;
      }
      .dim {
        color: #7c8aa0;
      }
      .micro {
        font-size: 0.72rem;
        line-height: 1.5;
      }
      .notice-warn {
        border: 1px solid rgba(251, 191, 36, 0.28);
        border-left: 3px solid rgba(251, 191, 36, 0.6);
        border-radius: 0.5rem;
        padding: 0.5rem 0.65rem;
        background: rgba(40, 32, 14, 0.55);
        color: #d6c08a;
      }
      .export-result {
        border: 1px solid rgba(74, 222, 128, 0.22);
        border-left: 3px solid rgba(74, 222, 128, 0.55);
        border-radius: 0.5rem;
        padding: 0.6rem 0.75rem;
        background: rgba(20, 33, 28, 0.5);
      }
      .mini-card {
        border: 1px solid rgba(148, 163, 184, 0.18);
        border-radius: 0.5rem;
        padding: 0.5rem 0.65rem;
        background: rgba(15, 23, 42, 0.55);
        display: flex;
        flex-direction: column;
        gap: 0.2rem;
        height: 100%;
      }
      .mono {
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      }
      .muted {
        color: #7c8aa0;
      }
      code {
        color: #fbbf24;
      }
    `,
  ],
})
export class FlPipelinePanel {
  protected readonly svc = inject(FlPipelineService);
  private readonly auth = inject(AuthService);

  readonly epsPresets = EPS_PRESETS;

  dsClients = 6;
  dsAlpha = 0.5;
  clientCount = 3;
  dropAt = false;
  roundClients = 3;
  roundCount = 1;
  roundEpsilon: number | null = null;
  sweepRounds = 2;
  sweepClients = 3;
  sweepEpochs = 1;
  sweepClip = 20.0;
  epsPreset = signal(EPS_PRESETS[1].label);
  epsValues = signal<(number | null)[]>(EPS_PRESETS[1].values);

  private readonly openLogs = signal<Record<number, boolean>>({});

  readonly status = computed<PipelineStatus | null>(() => this.svc.status());
  readonly dataset = computed(() => this.status()?.dataset ?? null);
  readonly datasetJob = computed(() => this.status()?.dataset_job ?? null);
  readonly sweep = computed(() => this.status()?.sweep ?? null);
  readonly spent = computed<PrivacySpent | null>(() => this.status()?.privacy_spent ?? null);
  readonly phases = computed(() => this.status()?.phases ?? []);
  readonly currentPhase = computed(() => this.status()?.round?.phase ?? 'IDLE');
  readonly participants = computed(
    () => (this.status()?.round?.config?.['participants'] as number[] | undefined) ?? [],
  );
  readonly history = computed(() => [...(this.status()?.history ?? [])].reverse());
  readonly clients = computed(() => this.status()?.clients ?? []);
  readonly sweepPoints = computed(() => this.sweep()?.points ?? []);
  /** Registered with the coordinator but not owned by the supervisor. */
  readonly unsupervised = computed(() => this.status()?.registered_not_supervised ?? []);
  readonly consentGranted = computed(() => this.auth.consentMap()['federated_training'] === true);

  readonly pipelineSteps = [
    {
      title: 'Dataset',
      ready: computed(() => this.dataset()?.ready === true),
      sub: computed(() =>
        this.dataset()?.ready
          ? `${this.dataset()?.total_train_samples} samples · ${this.dataset()?.shards.length} shards`
          : 'SNIPS not partitioned yet',
      ),
    },
    {
      title: 'Clients',
      ready: computed(() => (this.status()?.clients_alive ?? 0) > 0),
      sub: computed(() =>
        `${this.status()?.clients_alive ?? 0} process(es) alive, ` +
        `${this.status()?.registered?.registered_clients ?? 0} registered`,
      ),
    },
    {
      title: 'Round',
      ready: computed(() => (this.status()?.history_count ?? 0) > 0),
      sub: computed(() =>
        (this.status()?.history_count ?? 0) > 0
          ? `${this.status()?.history_count} round(s) aggregated`
          : 'no secure-aggregation round yet',
      ),
    },
    {
      title: 'Sweep',
      ready: computed(() => (this.sweep()?.points?.length ?? 0) > 0),
      sub: computed(() =>
        (this.sweep()?.points?.length ?? 0) > 0
          ? `${this.sweep()?.points?.length} ε point(s) measured`
          : 'ε sweep not run',
      ),
    },
    {
      title: 'Export',
      ready: computed(() => this.status()?.onnx_artifact_exists === true),
      sub: computed(() => {
        const s = this.status();
        if (!s?.onnx_artifact_exists) return 'no federated ONNX artifact yet';
        return `${s.federated_model_classes}-class federated artifact · served model untouched`;
      }),
    },
  ];

  readonly pctFormat = (v: number) => `${(v * 100).toFixed(1)}%`;

  readonly sweepLabels = computed(() =>
    (this.sweep()?.points ?? []).map((p) => p.epsilon_label),
  );

  readonly sweepSeries = computed<Series[]>(() => {
    const points = this.sweep()?.points ?? [];
    if (!points.length) return [];
    return [
      {
        label: 'final test accuracy',
        color: '#4f8cff',
        points: points.map((p) => p.final_accuracy),
      },
      {
        label: 'mean accuracy over rounds',
        color: '#a855f7',
        points: points.map((p) => p.mean_accuracy),
      },
    ];
  });

  readonly exportSizes = computed(() => {
    const res = this.svc.exportResult();
    if (!res) return null;
    // Prefer the parsed model card the service attaches; fall back to scraping
    // the module's stdout so an older log file still renders something.
    let sizes: Record<string, any> | null = res.sizes ?? null;
    if (!sizes) {
      const step = res.steps.find((s) => s.module.endsWith('export_onnx'));
      if (!step) return null;
      try {
        sizes = JSON.parse(step.stdout) as Record<string, any>;
      } catch {
        return null;
      }
    }
    if (!sizes || sizes['onnx_fp32_kb'] === undefined) return null;
    return {
      fp32: sizes['onnx_fp32_kb'],
      int8: sizes['onnx_int8_kb'],
      ratio: sizes['compression_ratio'],
      classes: sizes['num_classes'] ?? this.status()?.federated_model_classes ?? '?',
      servedByAssistant: sizes['served_by_assistant'] === true,
    };
  });

  constructor() {
    this.svc.startPolling();
  }

  ngOnDestroy(): void {
    this.svc.stopPolling();
  }

  phaseMeta(phase: string) {
    return PHASE_META[phase] ?? { label: phase, icon: 'question-circle', hint: '' };
  }

  phaseIcon(phase: string): string {
    return `bi-${this.phaseMeta(phase).icon}`;
  }

  isPast(phase: string): boolean {
    const order = this.phases();
    const current = order.indexOf(this.currentPhase());
    const idx = order.indexOf(phase);
    return current >= 0 && idx >= 0 && idx < current;
  }

  samplesFor(clientId: number): string {
    const found = this.status()?.registered?.clients?.find((c) => c.client_id === clientId);
    return found ? `${found.num_samples ?? '?'} samples` : 'registering…';
  }

  spentEpsilon(spent: PrivacySpent | null | undefined): string {
    if (!spent) return '—';
    return spent.epsilon === 0 && spent.note ? '∞ (no DP)' : String(spent.epsilon);
  }

  kb(bytes: number): string {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }

  logOpen(clientId: number): boolean {
    return this.openLogs()[clientId] === true;
  }

  logLines(clientId: number): string[] {
    return this.svc.clientLogs()[clientId]?.lines ?? ['loading…'];
  }

  async toggleLog(clientId: number): Promise<void> {
    const open = !this.logOpen(clientId);
    this.openLogs.update((map) => ({ ...map, [clientId]: open }));
    if (open) {
      await this.svc.loadClientLog(clientId, 30);
      const poll = setInterval(async () => {
        if (!this.logOpen(clientId)) {
          clearInterval(poll);
          return;
        }
        await this.svc.loadClientLog(clientId, 30);
      }, 2500);
    } else {
      this.svc.closeClientLog(clientId);
    }
  }

  selectPreset(preset: { label: string; values: (number | null)[] }): void {
    this.epsPreset.set(preset.label);
    this.epsValues.set(preset.values);
  }

  async prepareDataset(): Promise<void> {
    await this.svc.prepareDataset(Number(this.dsClients), Number(this.dsAlpha));
  }

  async spawn(): Promise<void> {
    await this.svc.spawnClients(Number(this.clientCount), this.dropAt ? 'COLLECT' : null);
    this.roundClients = Number(this.clientCount);
    this.sweepClients = Number(this.clientCount);
  }

  async stopAll(): Promise<void> {
    await this.svc.stopClients(null);
  }

  async stopOne(clientId: number): Promise<void> {
    await this.svc.stopClients([clientId]);
  }

  async runRound(): Promise<void> {
    await this.svc.runRound(Number(this.roundClients), Number(this.roundCount), this.roundEpsilon);
  }

  async startSweep(): Promise<void> {
    await this.svc.startSweep(
      this.epsValues(),
      Number(this.sweepRounds),
      Number(this.sweepClients),
      Number(this.sweepEpochs),
      Number(this.sweepClip),
    );
  }

  async exportOnnx(): Promise<void> {
    await this.svc.exportOnnx(true);
  }
}
