import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { ApiClient } from '../core/api-client.service';
import { toApiError } from '../core/auth.interceptor';
import {
  ClientLog,
  OnnxExportResult,
  PipelineStatus,
  RoundResult,
  SpawnResult,
} from '../core/api.types';
import { environment } from '../../environments/environment';

/**
 * ONE pipeline for the whole federated-learning demo.
 *
 * The coordinator lives inside the same FastAPI app that serves the assistant,
 * calendar and audit endpoints, and `/federated/pipeline/*` drives everything
 * else: SNIPS preparation, the independent client OS processes, secure-aggregation
 * rounds, the epsilon sweep and the ONNX export. There is no second server to
 * start and no extra shell to keep open — the Angular UI is the control plane.
 *
 * What is *not* collapsed: each client is still its own OS process holding its own
 * shard, and the coordinator still only ever receives masked uint32 vectors.
 */
@Injectable({ providedIn: 'root' })
export class FlPipelineService {
  private readonly api = inject(ApiClient);

  readonly status = signal<PipelineStatus | null>(null);
  readonly busy = signal(false);
  readonly busyAction = signal<string | null>(null);
  readonly error = signal<string | null>(null);
  readonly notice = signal<string | null>(null);
  readonly roundResults = signal<RoundResult[]>([]);
  readonly clientLogs = signal<Record<number, ClientLog>>({});
  readonly exportResult = signal<OnnxExportResult | null>(null);

  private timer: ReturnType<typeof setInterval> | null = null;

  /** Live polling — started when the pipeline tab is visible, stopped when it is not. */
  startPolling(): void {
    this.stopPolling();
    void this.refresh();
    this.timer = setInterval(() => void this.refresh(), environment.flPollMs);
  }

  stopPolling(): void {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  async refresh(): Promise<PipelineStatus | null> {
    try {
      const status = await firstValueFrom(
        this.api.get<PipelineStatus>('/federated/pipeline/status'),
      );
      this.status.set(status);
      return status;
    } catch (err) {
      this.error.set(toApiError(err).message);
      return null;
    }
  }

  /* ------------------------------ dataset ------------------------------ */

  async prepareDataset(clients: number, alpha: number): Promise<void> {
    await this.run('Preparing SNIPS dataset', async () => {
      const res = await firstValueFrom(
        this.api.post<{ started: boolean; reason?: string }>('/federated/pipeline/dataset/prepare', {
          clients,
          alpha,
        }),
      );
      this.notice.set(
        res.started
          ? `Dataset preparation started in the background (${clients} shards, Dirichlet α=${alpha}).`
          : `Not started: ${res.reason ?? 'already running'}`,
      );
      await this.refresh();
    });
  }

  /* ------------------------------ clients ------------------------------ */

  async spawnClients(count: number, dropAt: string | null): Promise<void> {
    await this.run(`Spawning ${count} client process(es)`, async () => {
      const res = await firstValueFrom(
        this.api.post<SpawnResult>('/federated/pipeline/clients/spawn', {
          count,
          start_id: 0,
          drop_at: dropAt,
        }),
      );
      if (res.error) {
        this.error.set(res.error);
        return;
      }
      const ids = res.spawned.map((c) => c.client_id).join(', ');
      this.notice.set(
        `Spawned client process(es) [${ids}] against ${res.spawned[0]?.server_url ?? 'the in-process coordinator'}.` +
          (res.errors?.length ? ` Errors: ${res.errors.join('; ')}` : ''),
      );
      await this.refresh();
    });
  }

  async stopClients(clientIds: number[] | null): Promise<void> {
    await this.run('Stopping client processes', async () => {
      const res = await firstValueFrom(
        this.api.post<{ stopped: number[] }>('/federated/pipeline/clients/stop', {
          client_ids: clientIds,
        }),
      );
      this.notice.set(`Stopped client process(es) [${res.stopped.join(', ')}].`);
      await this.refresh();
    });
  }

  async loadClientLog(clientId: number, lines = 25): Promise<void> {
    try {
      const log = await firstValueFrom(
        this.api.get<ClientLog>(`/federated/pipeline/clients/${clientId}/log`, { lines }),
      );
      this.clientLogs.update((map) => ({ ...map, [clientId]: log }));
    } catch (err) {
      this.error.set(toApiError(err).message);
    }
  }

  closeClientLog(clientId: number): void {
    this.clientLogs.update((map) => {
      const next = { ...map };
      delete next[clientId];
      return next;
    });
  }

  /* ------------------------------- rounds ------------------------------- */

  async runRound(nClients: number, rounds: number, epsilon: number | null): Promise<RoundResult[]> {
    let out: RoundResult[] = [];
    await this.run(`Running ${rounds} secure-aggregation round(s)`, async () => {
      out = await firstValueFrom(
        this.api.post<RoundResult[]>('/federated/round', {
          n_clients: nClients,
          rounds,
          epsilon,
          secure_aggregation: true,
        }),
      );
      this.roundResults.update((list) => [...out, ...list].slice(0, 20));
      this.notice.set(
        out.length
          ? `Round ${out[0].round_id}: accuracy ${(out[0].global_accuracy * 100).toFixed(2)}% ` +
            `with ${out[0].n_clients} clients, ${out[0].latency_ms} ms, ` +
            `${out[0].contributions.every((c) => c.masked) ? 'all updates masked' : 'WARNING: unmasked update'}.`
          : 'No round result returned.',
      );
      await this.refresh();
    });
    return out;
  }

  /* -------------------------------- sweep -------------------------------- */

  async startSweep(
    epsilons: (number | null)[],
    rounds: number,
    clientsPerRound: number,
    localEpochs: number,
    clipNorm: number,
  ): Promise<void> {
    await this.run('Starting epsilon sweep', async () => {
      const res = await firstValueFrom(
        this.api.post<{ started: boolean; reason?: string }>('/federated/pipeline/sweep/start', {
          epsilons,
          rounds,
          clients_per_round: clientsPerRound,
          local_epochs: localEpochs,
          clip_norm: clipNorm,
        }),
      );
      this.notice.set(
        res.started
          ? `Sweep started: ε = [${epsilons.map((e) => (e === null ? '∞' : e)).join(', ')}] × ${rounds} rounds.`
          : `Not started: ${res.reason ?? 'a sweep is already running'}`,
      );
      await this.refresh();
    });
  }

  /* -------------------------------- ONNX --------------------------------- */

  async exportOnnx(benchmark = true): Promise<void> {
    await this.run('Exporting global model to ONNX', async () => {
      const res = await firstValueFrom(
        this.api.post<OnnxExportResult>('/federated/pipeline/onnx/export', { benchmark }),
      );
      this.exportResult.set(res);
      this.notice.set(
        res.ok
          ? 'Global federated model exported to deployed_models/intent_model.onnx.'
          : 'Export reported a failure — see the step output below.',
      );
      await this.refresh();
    });
  }

  /* ------------------------------- helpers ------------------------------- */

  private async run(label: string, fn: () => Promise<void>): Promise<void> {
    this.busy.set(true);
    this.busyAction.set(label);
    this.error.set(null);
    try {
      await fn();
    } catch (err) {
      this.error.set(toApiError(err).message);
    } finally {
      this.busy.set(false);
      this.busyAction.set(null);
    }
  }

  clearNotice(): void {
    this.notice.set(null);
  }

  reset(): void {
    this.stopPolling();
    this.status.set(null);
    this.roundResults.set([]);
    this.clientLogs.set({});
    this.exportResult.set(null);
    this.notice.set(null);
    this.error.set(null);
  }
}
