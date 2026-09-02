import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AuditService, shortHash } from '../services/audit.service';
import { AuditRecord } from '../core/api.types';
import { Pill } from './pill';

/**
 * Tamper-evident audit trail.
 *
 * Two independent guarantees, both shown live:
 *  - a SHA-256 hash chain (`prev_hash` → `integrity_hash`) re-walked from genesis
 *    by `GET /audit/verify`, and
 *  - append-only DB triggers that reject UPDATE/DELETE on `audit_logs` outright.
 *
 * The chain strip draws each link so a broken record is obvious at a glance.
 */
@Component({
  selector: 'app-audit-panel',
  imports: [FormsModule, Pill],
  template: `
    <div class="row g-3">
      <div class="col-12 col-xl-4">
        <div class="card panel">
          <div class="card-header panel-head">
            <span><i class="bi bi-shield-check me-2"></i>Chain verification</span>
            <button class="btn btn-sm btn-outline-light" (click)="verify()" [disabled]="svc.busy()">
              <i class="bi bi-arrow-repeat me-1"></i>Verify
            </button>
          </div>
          <div class="card-body">
            @if (svc.verification(); as v) {
              <div class="verdict" [class.ok]="v.valid" [class.bad]="!v.valid">
                <i class="bi" [class.bi-patch-check-fill]="v.valid" [class.bi-exclamation-octagon-fill]="!v.valid"></i>
                <div>
                  <div class="verdict-title">{{ v.valid ? 'CHAIN INTACT' : 'CHAIN BROKEN' }}</div>
                  <div class="verdict-sub">{{ v.message }}</div>
                </div>
              </div>
              <div class="kv mt-3">
                <div class="kv-row">
                  <span class="k">records</span><span class="v">{{ v.total_records }}</span>
                </div>
                <div class="kv-row">
                  <span class="k">valid</span>
                  <span class="v">
                    <app-pill [tone]="v.valid ? 'ok' : 'bad'">{{ v.valid }}</app-pill>
                  </span>
                </div>
                <div class="kv-row">
                  <span class="k">broken_at_id</span>
                  <span class="v mono">{{ v.broken_at_id ?? '—' }}</span>
                </div>
              </div>
            } @else {
              <p class="muted small">
                Press <strong>Verify</strong> to walk the hash chain from the genesis record.
              </p>
            }

            <hr class="sep" />
            <h6 class="sub">Append-only at the database layer</h6>
            <p class="muted micro mb-2">
              Triggers installed by Alembic migration <code>b1a7c3d9e042</code> reject modification
              even from a DBA session — the app cannot rewrite history either.
            </p>
            <pre class="sql"><code>UPDATE audit_logs SET reason='x' WHERE id=1;
-- ERROR: AuditLog is append-only: updates are prohibited

DELETE FROM audit_logs WHERE id=1;
-- ERROR: AuditLog is append-only: deletes are prohibited</code></pre>
          </div>
        </div>

        <div class="card panel mt-3">
          <div class="card-header panel-head">
            <span><i class="bi bi-link-45deg me-2"></i>Chain links</span>
            <app-pill [tone]="allLinked() ? 'ok' : 'bad'" icon="link">
              {{ linkedCount() }}/{{ chain().length }} linked
            </app-pill>
          </div>
          <div class="card-body">
            <div class="chain">
              @for (link of chain(); track link.id) {
                <div class="chain-node" [class.ok]="link.ok" [class.bad]="!link.ok" [title]="link.why">
                  <i class="bi" [class.bi-link-45deg]="link.ok" [class.bi-link-45deg]="!link.ok"></i>
                  <span class="cid">#{{ link.id }}</span>
                </div>
              } @empty {
                <span class="muted small">No records loaded yet.</span>
              }
            </div>
            <p class="muted micro mb-0 mt-2">
              Each node's <code>prev_hash</code> must equal the previous row's
              <code>integrity_hash</code>. Hover a node to see the comparison.
            </p>
          </div>
        </div>
      </div>

      <div class="col-12 col-xl-8">
        <div class="card panel">
          <div class="card-header panel-head">
            <span><i class="bi bi-list-check me-2"></i>Audit records</span>
            <div class="d-flex gap-2 align-items-center">
              <input
                class="form-control form-control-sm search"
                name="q"
                [(ngModel)]="query"
                placeholder="filter action / reason…"
              />
              <select class="form-select form-select-sm filter" name="action" [(ngModel)]="actionFilter">
                <option value="">all actions</option>
                @for (a of availableActions(); track a) {
                  <option [value]="a">{{ a }}</option>
                }
              </select>
              <button class="btn btn-sm btn-outline-light" (click)="reload()" [disabled]="svc.busy()">
                <i class="bi bi-arrow-clockwise"></i>
              </button>
            </div>
          </div>
          <div class="card-body">
            <p class="muted micro mb-2">
              Scoped to your user by the backend ({{ shown().length }} of {{ svc.records().length }}
              shown). Note the <em>reason</em> column: it never contains an event title or message
              body, because those are sensitive.
            </p>
            <div class="table-responsive audit-table">
              <table class="table table-sm align-middle data">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Action</th>
                    <th>Data type</th>
                    <th>Reason</th>
                    <th>Location</th>
                    <th>integrity_hash</th>
                    <th>When</th>
                  </tr>
                </thead>
                <tbody>
                  @for (r of shown(); track r.id) {
                    <tr>
                      <td class="mono dim">{{ r.id }}</td>
                      <td><span class="action">{{ r.action }}</span></td>
                      <td class="small dim">{{ r.data_type }}</td>
                      <td class="reason">{{ r.reason }}</td>
                      <td>
                        <app-pill [tone]="r.external_processing ? 'bad' : 'ok'" [icon]="r.external_processing ? 'cloud-arrow-up' : 'house'">
                          {{ r.processing_location }}
                        </app-pill>
                      </td>
                      <td class="mono hash" [title]="r.integrity_hash ?? ''">
                        {{ short(r.integrity_hash) }}
                      </td>
                      <td class="mono small dim">{{ fmt(r.created_at) }}</td>
                    </tr>
                  } @empty {
                    <tr>
                      <td colspan="7" class="muted small py-3 text-center">
                        No audit records match this filter.
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
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
      .verdict {
        display: flex;
        gap: 0.75rem;
        align-items: center;
        border-radius: 0.6rem;
        padding: 0.75rem 0.9rem;
        border: 1px solid rgba(148, 163, 184, 0.18);
      }
      .verdict i {
        font-size: 1.9rem;
      }
      .verdict.ok {
        background: rgba(34, 197, 94, 0.1);
        border-color: rgba(34, 197, 94, 0.35);
        color: #4ade80;
      }
      .verdict.bad {
        background: rgba(239, 68, 68, 0.1);
        border-color: rgba(239, 68, 68, 0.4);
        color: #f87171;
      }
      .verdict-title {
        font-weight: 700;
        font-size: 0.95rem;
        letter-spacing: 0.04em;
      }
      .verdict-sub {
        color: #94a3b8;
        font-size: 0.76rem;
        line-height: 1.45;
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
        padding: 0.3rem 0.6rem;
        font-size: 0.78rem;
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
      .chain {
        display: flex;
        flex-wrap: wrap;
        gap: 0.25rem;
      }
      .chain-node {
        display: inline-flex;
        align-items: center;
        gap: 0.2rem;
        border-radius: 0.4rem;
        padding: 0.15rem 0.4rem;
        font-size: 0.68rem;
        border: 1px solid transparent;
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      }
      .chain-node.ok {
        color: #4ade80;
        background: rgba(34, 197, 94, 0.1);
        border-color: rgba(34, 197, 94, 0.3);
      }
      .chain-node.bad {
        color: #fca5a5;
        background: rgba(239, 68, 68, 0.14);
        border-color: rgba(239, 68, 68, 0.45);
      }
      .search {
        width: 12rem;
      }
      .filter {
        width: 11rem;
      }
      .audit-table {
        max-height: 34rem;
        overflow: auto;
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
        position: sticky;
        top: 0;
        background: #0d1524;
        z-index: 1;
      }
      table.data td {
        border-bottom: 1px solid rgba(148, 163, 184, 0.08);
      }
      .action {
        color: #93c5fd;
        font-weight: 600;
        font-size: 0.74rem;
      }
      .reason {
        color: #94a3b8;
        font-size: 0.74rem;
        max-width: 26rem;
      }
      .hash {
        color: #a5f3fc;
        font-size: 0.7rem;
      }
      .sql {
        background: #070b14;
        border: 1px solid rgba(148, 163, 184, 0.18);
        border-radius: 0.5rem;
        padding: 0.55rem 0.7rem;
        margin: 0;
        color: #a5f3fc;
        font-size: 0.7rem;
        overflow: auto;
      }
      .sep {
        border-color: rgba(148, 163, 184, 0.16);
        margin: 1rem 0;
      }
      .sub {
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #94a3b8;
      }
      .muted {
        color: #7c8aa0;
      }
      .micro {
        font-size: 0.74rem;
        line-height: 1.5;
      }
      .mono {
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      }
      .dim {
        color: #64748b;
      }
      code {
        color: #fbbf24;
      }
    `,
  ],
})
export class AuditPanel {
  protected readonly svc = inject(AuditService);

  query = '';
  actionFilter = '';

  readonly chain = computed(() => this.svc.chainChecks());
  readonly linkedCount = computed(() => this.chain().filter((l) => l.ok).length);
  readonly allLinked = computed(
    () => this.chain().length > 0 && this.chain().every((l) => l.ok),
  );

  readonly availableActions = computed(() =>
    [...new Set(this.svc.records().map((r) => r.action))].sort(),
  );

  readonly shown = computed(() => {
    const q = this.query.trim().toLowerCase();
    const action = this.actionFilter;
    return this.svc
      .records()
      .filter((r) => (action ? r.action === action : true))
      .filter((r) =>
        q ? `${r.action} ${r.reason} ${r.data_type}`.toLowerCase().includes(q) : true,
      )
      .slice()
      .reverse();
  });

  constructor() {
    void this.reload();
    void this.verify();
  }

  short(hash: string | null): string {
    return shortHash(hash, 16);
  }

  fmt(value: string): string {
    const d = new Date(value);
    return Number.isNaN(d.getTime())
      ? value
      : d.toLocaleString(undefined, {
          month: 'short',
          day: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
        });
  }

  async reload(): Promise<void> {
    await this.svc.load(300);
  }

  async verify(): Promise<void> {
    await this.svc.verify();
    await this.reload();
  }
}
