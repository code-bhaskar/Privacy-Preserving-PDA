import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AuthService, CONSENT_CATEGORIES } from '../services/auth.service';
import { PrivacyService } from '../services/privacy.service';
import { ConsentCategory, PrivacyPosture } from '../core/api.types';
import { Pill } from './pill';

interface JwtPart {
  header: Record<string, unknown> | null;
  payload: Record<string, unknown> | null;
  signatureLength: number;
  expiresAt: string | null;
}

/**
 * Privacy & data tab — the evidence screen.
 *
 * Four things a reviewer usually asks for, all live:
 *   1. consent switches (and the 403 refusal they gate),
 *   2. an AES-256-GCM round trip on arbitrary text,
 *   3. an IDOR probe proving cross-user reads return 404 (not 403),
 *   4. the honest implemented-vs-architecture-only posture map.
 */
@Component({
  selector: 'app-privacy-panel',
  imports: [FormsModule, Pill],
  template: `
    <div class="row g-3">
      <div class="col-12 col-lg-6">
        <div class="card panel">
          <div class="card-header panel-head">
            <span><i class="bi bi-toggles me-2"></i>Consent (FR-3 gate)</span>
            <div class="d-flex gap-2">
              <button class="btn btn-sm btn-outline-success" (click)="grantAll()">Grant all</button>
              <button class="btn btn-sm btn-outline-warning" (click)="revokeAll()">Revoke all</button>
            </div>
          </div>
          <div class="card-body">
            <p class="muted micro mb-3">
              Nothing is processed without an explicit grant. Flip one off and the matching endpoint
              answers <strong>403 Consent not granted</strong> — try it in the Assistant tab.
            </p>
            @for (c of categories; track c.key) {
              <div class="consent-row">
                <div class="form-check form-switch mb-0">
                  <input
                    class="form-check-input"
                    type="checkbox"
                    role="switch"
                    [id]="'consent-' + c.key"
                    [checked]="granted()[c.key] === true"
                    (change)="toggle(c.key, $event)"
                  />
                </div>
                <label class="consent-body" [for]="'consent-' + c.key">
                  <span class="consent-label">
                    {{ c.label }}
                    <code>{{ c.key }}</code>
                  </span>
                  <span class="consent-hint">{{ c.hint }}</span>
                </label>
                <app-pill [tone]="granted()[c.key] ? 'ok' : 'bad'" [icon]="granted()[c.key] ? 'check-lg' : 'slash-circle'">
                  {{ granted()[c.key] ? 'granted' : 'denied' }}
                </app-pill>
              </div>
            }
          </div>
        </div>

        <div class="card panel mt-3">
          <div class="card-header panel-head">
            <span><i class="bi bi-key me-2"></i>Your JWT</span>
            <app-pill tone="info" icon="person-badge">identity from token only</app-pill>
          </div>
          <div class="card-body">
            @if (jwt(); as t) {
              <div class="kv mb-2">
                <div class="kv-row">
                  <span class="k">header</span>
                  <span class="v mono">{{ json(t.header) }}</span>
                </div>
                <div class="kv-row">
                  <span class="k">payload</span>
                  <span class="v mono">{{ json(t.payload) }}</span>
                </div>
                <div class="kv-row">
                  <span class="k">signature</span>
                  <span class="v mono">{{ t.signatureLength }} chars (HS256, not decoded)</span>
                </div>
                <div class="kv-row">
                  <span class="k">expires</span>
                  <span class="v">{{ t.expiresAt ?? '—' }}</span>
                </div>
              </div>
              <p class="muted micro mb-0">
                <code>sub</code> is the only user id the backend trusts. No request body in this API
                carries a <code>user_id</code> — that is the IDOR fix.
              </p>
            } @else {
              <p class="muted small mb-0">No token in this session.</p>
            }
          </div>
        </div>
      </div>

      <div class="col-12 col-lg-6">
        <div class="card panel">
          <div class="card-header panel-head">
            <span><i class="bi bi-lock me-2"></i>AES-256-GCM round trip</span>
            @if (svc.encryptResult(); as r) {
              <app-pill [tone]="r.roundtrip_ok ? 'ok' : 'bad'" icon="arrow-left-right">
                {{ r.roundtrip_ok ? 'decrypt matches' : 'MISMATCH' }}
              </app-pill>
            }
          </div>
          <div class="card-body">
            <form (ngSubmit)="encrypt()" class="d-flex gap-2 mb-3">
              <input
                class="form-control form-control-sm"
                name="plain"
                [(ngModel)]="plaintext"
                placeholder="meeting with client at 3pm"
              />
              <button class="btn btn-sm btn-primary px-3" type="submit" [disabled]="svc.busy()">
                <i class="bi bi-lock-fill"></i>
              </button>
            </form>

            @if (svc.encryptResult(); as r) {
              <div class="crypto">
                <div class="crypto-row">
                  <span class="lbl">plaintext</span>
                  <span class="val plain">{{ svc.encryptInput() }}</span>
                </div>
                <div class="crypto-row">
                  <span class="lbl">algorithm</span>
                  <span class="val"><app-pill tone="accent">{{ r.algorithm }}</app-pill></span>
                </div>
                <div class="crypto-row">
                  <span class="lbl">ciphertext</span>
                  <span class="val ct mono">{{ r.ciphertext_b64 }}</span>
                </div>
              </div>
              <p class="muted micro mt-2 mb-0">
                The same routine encrypts <code>calendar_events.title</code>,
                <code>reminders.text</code> and <code>messages.content</code> before they hit the
                database, with your user id as Authenticated Additional Data.
              </p>
            } @else {
              <p class="muted small mb-0">Type something and lock it to see live ciphertext.</p>
            }
          </div>
        </div>

        <div class="card panel mt-3">
          <div class="card-header panel-head">
            <span><i class="bi bi-person-slash me-2"></i>IDOR probe</span>
            <app-pill tone="ok" icon="shield-check">expect 404, never 403</app-pill>
          </div>
          <div class="card-body">
            <p class="muted micro mb-2">
              Ask for somebody else's record by guessing an id. A vulnerable API returns the data
              (200) or a <em>Forbidden</em> (403) that confirms the account exists. This one answers
              <strong>404</strong>, byte-identical to a record that never existed.
            </p>
            <form (ngSubmit)="probe()" class="d-flex gap-2 mb-3">
              <div class="input-group input-group-sm">
                <span class="input-group-text">GET /api/v1/users/</span>
                <input
                  class="form-control"
                  type="number"
                  name="probeId"
                  [(ngModel)]="probeId"
                  min="1"
                  style="max-width: 6rem"
                />
              </div>
              <button class="btn btn-sm btn-outline-danger px-3" type="submit" [disabled]="svc.busy()">
                <i class="bi bi-send me-1"></i>Probe
              </button>
              <button class="btn btn-sm btn-outline-secondary px-3" type="button" (click)="probeSelf()">
                Probe my own id ({{ auth.user()?.id }})
              </button>
            </form>

            @for (p of svc.probes(); track p.at + p.targetUserId) {
              <div class="probe" [class.safe]="p.verdict === 'safe'" [class.leak]="p.verdict === 'leak'">
                <div class="probe-head">
                  <span class="mono">GET /users/{{ p.targetUserId }}</span>
                  <app-pill [tone]="p.verdict === 'safe' ? 'ok' : 'bad'" [icon]="p.verdict === 'safe' ? 'check-lg' : 'exclamation-triangle'">
                    HTTP {{ p.status }}
                  </app-pill>
                  <span class="at ms-auto">{{ p.at }}</span>
                </div>
                <div class="probe-detail mono">"{{ p.detail }}"</div>
                <div class="probe-note">{{ p.note }}</div>
              </div>
            } @empty {
              <p class="muted small mb-0">No probes run yet.</p>
            }
          </div>
        </div>
      </div>

      <div class="col-12">
        <div class="card panel">
          <div class="card-header panel-head">
            <span><i class="bi bi-map me-2"></i>Privacy posture — implemented vs architecture-only</span>
            <div class="d-flex gap-2 flex-wrap">
              <app-pill tone="ok">IMPLEMENTED {{ count('IMPLEMENTED') }}</app-pill>
              <app-pill tone="warn">not built {{ count('NOT_IMPLEMENTED') + count('ARCHITECTURE_ONLY') + count('FUTURE_WORK') + count('NOT_DONE') }}</app-pill>
              <button class="btn btn-sm btn-outline-light" (click)="reloadPosture()">
                <i class="bi bi-arrow-clockwise"></i>
              </button>
            </div>
          </div>
          <div class="card-body">
            <p class="muted micro mb-3">
              Served by <code>GET /api/v1/privacy/posture</code>. Overclaiming is the easy failure
              mode in a privacy project, so this table is the answer to “what is actually real?”.
            </p>
            <div class="table-responsive">
              <table class="table table-sm align-middle data">
                <thead>
                  <tr>
                    <th style="width: 22%">Technology</th>
                    <th style="width: 20%">Status</th>
                    <th>Notes</th>
                  </tr>
                </thead>
                <tbody>
                  @for (row of svc.posture(); track row.technology) {
                    <tr>
                      <td class="tech">{{ row.technology }}</td>
                      <td><app-pill [tone]="toneFor(row)" [icon]="iconFor(row)">{{ row.status }}</app-pill></td>
                      <td class="notes">{{ row.notes }}</td>
                    </tr>
                  } @empty {
                    <tr><td colspan="3" class="muted small py-3 text-center">Loading posture…</td></tr>
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
      .consent-row {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        padding: 0.5rem 0.6rem;
        border: 1px solid rgba(148, 163, 184, 0.14);
        border-radius: 0.5rem;
        margin-bottom: 0.4rem;
        background: rgba(7, 11, 20, 0.55);
      }
      .consent-body {
        display: flex;
        flex-direction: column;
        min-width: 0;
        flex: 1 1 auto;
        cursor: pointer;
      }
      .consent-label {
        color: #e2e8f0;
        font-size: 0.85rem;
        font-weight: 600;
        display: flex;
        gap: 0.45rem;
        align-items: baseline;
        flex-wrap: wrap;
      }
      .consent-label code {
        font-size: 0.68rem;
        color: #7dd3fc;
      }
      .consent-hint {
        color: #7c8aa0;
        font-size: 0.72rem;
        line-height: 1.45;
      }
      .kv {
        border: 1px solid rgba(148, 163, 184, 0.16);
        border-radius: 0.5rem;
        overflow: hidden;
      }
      .kv-row {
        display: flex;
        gap: 1rem;
        padding: 0.3rem 0.6rem;
        font-size: 0.76rem;
        border-bottom: 1px solid rgba(148, 163, 184, 0.1);
      }
      .kv-row:last-child {
        border-bottom: 0;
      }
      .kv-row .k {
        color: #7dd3fc;
        flex: 0 0 5.5rem;
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      }
      .kv-row .v {
        color: #e2e8f0;
        word-break: break-word;
      }
      .crypto {
        background: #070b14;
        border: 1px solid rgba(148, 163, 184, 0.18);
        border-radius: 0.5rem;
        padding: 0.6rem 0.75rem;
        display: flex;
        flex-direction: column;
        gap: 0.4rem;
      }
      .crypto-row {
        display: flex;
        gap: 0.75rem;
        align-items: baseline;
        font-size: 0.78rem;
      }
      .crypto-row .lbl {
        flex: 0 0 5.5rem;
        color: #7c8aa0;
        text-transform: uppercase;
        font-size: 0.64rem;
        letter-spacing: 0.06em;
      }
      .crypto-row .val {
        word-break: break-all;
        color: #e2e8f0;
      }
      .val.plain {
        color: #fbbf24;
      }
      .val.ct {
        color: #a5f3fc;
        font-size: 0.72rem;
      }
      .probe {
        border-radius: 0.5rem;
        padding: 0.5rem 0.7rem;
        margin-bottom: 0.4rem;
        border: 1px solid rgba(148, 163, 184, 0.16);
        background: rgba(7, 11, 20, 0.55);
      }
      .probe.safe {
        border-color: rgba(34, 197, 94, 0.35);
        background: rgba(34, 197, 94, 0.07);
      }
      .probe.leak {
        border-color: rgba(239, 68, 68, 0.4);
        background: rgba(239, 68, 68, 0.08);
      }
      .probe-head {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        font-size: 0.78rem;
        color: #cbd5e1;
      }
      .probe-head .at {
        color: #64748b;
        font-size: 0.68rem;
      }
      .probe-detail {
        color: #94a3b8;
        font-size: 0.74rem;
        margin-top: 0.2rem;
        word-break: break-word;
      }
      .probe-note {
        color: #7c8aa0;
        font-size: 0.72rem;
        margin-top: 0.15rem;
      }
      table.data {
        color: #cbd5e1;
        font-size: 0.8rem;
        margin-bottom: 0;
      }
      table.data thead th {
        color: #7c8aa0;
        font-size: 0.68rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        border-bottom: 1px solid rgba(148, 163, 184, 0.18);
      }
      table.data td {
        border-bottom: 1px solid rgba(148, 163, 184, 0.08);
      }
      .tech {
        color: #f1f5f9;
        font-weight: 600;
      }
      .notes {
        color: #94a3b8;
        font-size: 0.76rem;
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
      code {
        color: #fbbf24;
      }
      :host ::ng-deep .input-group-text {
        background: #0b1220;
        border-color: rgba(148, 163, 184, 0.28);
        color: #94a3b8;
        font-size: 0.74rem;
      }
    `,
  ],
})
export class PrivacyPanel {
  protected readonly auth = inject(AuthService);
  protected readonly svc = inject(PrivacyService);

  readonly categories = CONSENT_CATEGORIES;
  plaintext = 'meeting with client at 3pm';
  probeId = 999999;

  readonly granted = computed(() => this.auth.consentMap());

  readonly jwt = computed<JwtPart | null>(() => decodeJwt(this.auth.token()));

  constructor() {
    void this.reloadPosture();
    void this.auth.refreshConsents();
  }

  async reloadPosture(): Promise<void> {
    await this.svc.loadPosture();
  }

  json(value: unknown): string {
    return value ? JSON.stringify(value) : '—';
  }

  async toggle(category: ConsentCategory, event: Event): Promise<void> {
    const checked = (event.target as HTMLInputElement).checked;
    try {
      await this.auth.setConsent(category, checked);
    } catch {
      await this.auth.refreshConsents();
    }
  }

  async grantAll(): Promise<void> {
    await this.auth.grantAllConsents();
  }

  async revokeAll(): Promise<void> {
    for (const c of this.categories) {
      await this.auth.setConsent(c.key, false);
    }
  }

  async encrypt(): Promise<void> {
    if (!this.plaintext.trim()) return;
    await this.svc.encryptDemo(this.plaintext);
  }

  async probe(): Promise<void> {
    await this.svc.probeUser(Number(this.probeId));
  }

  async probeSelf(): Promise<void> {
    const id = this.auth.user()?.id;
    if (id !== undefined) await this.svc.probeUser(id);
  }

  count(status: string): number {
    return this.svc.posture().filter((p: PrivacyPosture) => p.status === status).length;
  }

  toneFor(row: PrivacyPosture): 'ok' | 'info' | 'warn' | 'bad' | 'muted' | 'accent' {
    switch (row.status) {
      case 'IMPLEMENTED':
        return 'ok';
      case 'DEPLOYMENT_REQUIREMENT':
        return 'info';
      case 'ARCHITECTURE_ONLY':
      case 'FUTURE_WORK':
        return 'warn';
      case 'NOT_IMPLEMENTED':
      case 'NOT_DONE':
        return 'bad';
      default:
        return 'muted';
    }
  }

  iconFor(row: PrivacyPosture): string {
    switch (row.status) {
      case 'IMPLEMENTED':
        return 'check-circle';
      case 'DEPLOYMENT_REQUIREMENT':
        return 'hdd-network';
      case 'ARCHITECTURE_ONLY':
      case 'FUTURE_WORK':
        return 'compass';
      case 'NOT_IMPLEMENTED':
      case 'NOT_DONE':
        return 'x-circle';
      default:
        return 'question-circle';
    }
  }
}

function decodeJwt(token: string | null): JwtPart | null {
  if (!token) return null;
  const [header, payload, signature] = token.split('.');
  if (!header || !payload) return null;
  return {
    header: decodeSegment(header),
    payload: decodeSegment(payload),
    signatureLength: signature?.length ?? 0,
    expiresAt: expiresLabel(decodeSegment(payload)),
  };
}

function decodeSegment(segment: string): Record<string, unknown> | null {
  try {
    const normalised = segment.replace(/-/g, '+').replace(/_/g, '/');
    const padded = normalised.padEnd(Math.ceil(normalised.length / 4) * 4, '=');
    const json = decodeURIComponent(
      atob(padded)
        .split('')
        .map((c) => `%${c.charCodeAt(0).toString(16).padStart(2, '0')}`)
        .join(''),
    );
    return JSON.parse(json) as Record<string, unknown>;
  } catch {
    return null;
  }
}

function expiresLabel(payload: Record<string, unknown> | null): string | null {
  const exp = payload?.['exp'];
  if (typeof exp !== 'number') return null;
  const date = new Date(exp * 1000);
  const mins = Math.round((date.getTime() - Date.now()) / 60000);
  return `${date.toLocaleString()} (${mins > 0 ? `${mins} min left` : 'expired'})`;
}
