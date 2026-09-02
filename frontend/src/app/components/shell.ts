import { Component, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { AuthService } from '../services/auth.service';
import { ApiClient } from '../core/api-client.service';
import { DataService } from '../services/data.service';
import { AssistantPanel } from './assistant-panel';
import { SchedulerPanel } from './scheduler-panel';
import { PrivacyPanel } from './privacy-panel';
import { AuditPanel } from './audit-panel';
import { FlPipelinePanel } from './fl-pipeline-panel';
import { Pill } from './pill';

type TabId = 'assistant' | 'scheduler' | 'privacy' | 'audit' | 'federated';

const TABS: { id: TabId; label: string; icon: string; hint: string }[] = [
  { id: 'assistant', label: 'Assistant', icon: 'chat-dots', hint: 'On-device intent (ONNX) + saliency' },
  { id: 'scheduler', label: 'Calendar & reminders', icon: 'calendar3', hint: 'Encrypted at rest' },
  { id: 'privacy', label: 'Privacy & data', icon: 'shield-lock', hint: 'Consent, AES-GCM, IDOR, posture' },
  { id: 'audit', label: 'Audit trail', icon: 'list-check', hint: 'SHA-256 hash chain + append-only' },
  { id: 'federated', label: 'Federated pipeline', icon: 'diagram-3', hint: 'Secure aggregation + DP, one pipeline' },
];

/**
 * Authenticated shell: top bar (identity, backend health, logout) and the five
 * demo tabs. The federated tab is the only one that polls, so polling is started
 * on entry and stopped on leave.
 */
@Component({
  selector: 'app-shell',
  imports: [Pill, AssistantPanel, SchedulerPanel, PrivacyPanel, AuditPanel, FlPipelinePanel],
  template: `
    <div class="app-shell">
      <nav class="navbar navbar-expand-lg app-nav">
        <div class="container-fluid px-3 px-lg-4">
          <span class="navbar-brand d-flex align-items-center gap-2">
            <i class="bi bi-shield-lock-fill brand-icon"></i>
            <span class="brand-text">
              PPDA
              <small>demonstration frontend</small>
            </span>
          </span>

          <div class="d-flex align-items-center gap-2 flex-wrap">
            <app-pill [tone]="health() === 'ok' ? 'ok' : 'bad'" icon="activity">
              {{ health() === 'ok' ? 'API up' : 'API down' }}
            </app-pill>
            <span class="who">
              <i class="bi bi-person-circle me-1"></i>{{ auth.user()?.email ?? '—' }}
              <span class="uid">#{{ auth.user()?.id }}</span>
            </span>
            <a class="btn btn-sm btn-outline-secondary" href="/docs" target="_blank" rel="noopener">
              <i class="bi bi-book me-1"></i>Swagger
            </a>
            <button type="button" class="btn btn-sm btn-outline-danger" (click)="logout()">
              <i class="bi bi-box-arrow-right me-1"></i>Logout
            </button>
          </div>
        </div>
      </nav>

      <div class="tabs-wrap">
        <ul class="nav nav-tabs app-tabs" role="tablist">
          @for (tab of tabs; track tab.id) {
            <li class="nav-item" role="presentation">
              <button
                type="button"
                class="nav-link"
                [class.active]="activeTab() === tab.id"
                (click)="select(tab.id)"
                [attr.aria-selected]="activeTab() === tab.id"
              >
                <i class="bi" [class]="tabIcon(tab.icon)"></i>
                <span class="tab-label">{{ tab.label }}</span>
                <span class="tab-hint">{{ tab.hint }}</span>
              </button>
            </li>
          }
        </ul>
      </div>

      <main class="container-fluid px-3 px-lg-4 py-4">
        @switch (activeTab()) {
          @case ('assistant') {
            <app-assistant-panel />
          }
          @case ('scheduler') {
            <app-scheduler-panel />
          }
          @case ('privacy') {
            <app-privacy-panel />
          }
          @case ('audit') {
            <app-audit-panel />
          }
          @case ('federated') {
            <app-fl-pipeline-panel />
          }
        }
      </main>

      <footer class="app-footer">
        <span>
          Angular 20 · Bootstrap 5.3.3 · HTML5 — demonstration UI for the PPDA FastAPI backend.
        </span>
        <span class="mono">relative API base &#8594; dev-server proxy &#8594; :8000</span>
      </footer>
    </div>
  `,
  styles: [
    `
      .app-shell {
        min-height: 100vh;
        display: flex;
        flex-direction: column;
        background:
          radial-gradient(1100px 500px at 100% 0%, rgba(139, 92, 246, 0.14), transparent 60%),
          radial-gradient(900px 480px at 0% 0%, rgba(79, 140, 255, 0.16), transparent 55%),
          #070b14;
      }
      .app-nav {
        background: rgba(9, 14, 25, 0.92);
        border-bottom: 1px solid rgba(148, 163, 184, 0.16);
        padding: 0.6rem 0;
        backdrop-filter: blur(6px);
      }
      .navbar-brand {
        color: #f1f5f9;
        font-weight: 700;
        letter-spacing: 0.02em;
      }
      .brand-icon {
        font-size: 1.35rem;
        color: #93c5fd;
      }
      .brand-text {
        display: flex;
        flex-direction: column;
        line-height: 1.1;
      }
      .brand-text small {
        font-size: 0.66rem;
        font-weight: 500;
        color: #8ea0b8;
        letter-spacing: 0.08em;
        text-transform: uppercase;
      }
      .who {
        color: #cbd5e1;
        font-size: 0.82rem;
      }
      .uid {
        color: #64748b;
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
        margin-left: 0.25rem;
      }
      .tabs-wrap {
        background: rgba(9, 14, 25, 0.7);
        border-bottom: 1px solid rgba(148, 163, 184, 0.16);
        overflow-x: auto;
      }
      .app-tabs {
        border-bottom: 0;
        flex-wrap: nowrap;
        gap: 0.25rem;
        padding: 0.4rem 0.75rem 0;
      }
      .app-tabs .nav-link {
        border: 1px solid transparent;
        border-bottom: none;
        color: #93a4bd;
        background: transparent;
        border-radius: 0.6rem 0.6rem 0 0;
        display: flex;
        flex-direction: column;
        align-items: flex-start;
        gap: 0.05rem;
        padding: 0.45rem 0.85rem;
        white-space: nowrap;
      }
      .app-tabs .nav-link i {
        font-size: 0.95rem;
      }
      .tab-label {
        font-size: 0.85rem;
        font-weight: 600;
      }
      .tab-hint {
        font-size: 0.66rem;
        color: #64748b;
      }
      .app-tabs .nav-link.active {
        background: #0d1524;
        border-color: rgba(148, 163, 184, 0.22);
        color: #e2e8f0;
      }
      .app-tabs .nav-link.active .tab-hint {
        color: #7dd3fc;
      }
      main {
        flex: 1 1 auto;
      }
      .app-footer {
        border-top: 1px solid rgba(148, 163, 184, 0.14);
        color: #64748b;
        font-size: 0.72rem;
        padding: 0.75rem 1.25rem;
        display: flex;
        justify-content: space-between;
        gap: 1rem;
        flex-wrap: wrap;
      }
      .mono {
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      }
    `,
  ],
})
export class Shell {
  protected readonly auth = inject(AuthService);
  private readonly api = inject(ApiClient);
  private readonly data = inject(DataService);

  readonly tabs = TABS;
  readonly activeTab = signal<TabId>('assistant');
  readonly health = signal<'ok' | 'down'>('down');

  constructor() {
    void this.checkHealth();
    setInterval(() => void this.checkHealth(), 15000);
  }

  tabIcon(name: string): string {
    return `bi-${name}`;
  }

  select(tab: TabId): void {
    this.activeTab.set(tab);
    if (tab === 'scheduler') {
      void this.data.loadEvents();
      void this.data.loadReminders();
    }
  }

  async logout(): Promise<void> {
    await this.auth.logout();
    this.data.clear();
  }

  private async checkHealth(): Promise<void> {
    try {
      const res = await firstValueFrom(this.api.health());
      this.health.set(res?.status === 'ok' ? 'ok' : 'down');
    } catch {
      this.health.set('down');
    }
  }
}
