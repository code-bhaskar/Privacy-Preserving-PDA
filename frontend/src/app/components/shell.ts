import { Component, inject, OnDestroy, signal } from '@angular/core';
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
  { id: 'assistant', label: 'Assistant', icon: 'chat-dots', hint: 'Chat and local summary' },
  { id: 'scheduler', label: 'Calendar', icon: 'calendar3', hint: 'Events and reminders' },
  { id: 'privacy', label: 'Privacy', icon: 'shield-lock', hint: 'Consent and data controls' },
  { id: 'audit', label: 'Audit trail', icon: 'list-check', hint: 'Integrity history' },
  { id: 'federated', label: 'Federated ML', icon: 'diagram-3', hint: 'Advanced training workspace' },
];

const PAGE_META: Record<TabId, { eyebrow: string; title: string; description: string }> = {
  assistant: {
    eyebrow: 'Private assistant',
    title: 'Ask, act, and summarize',
    description: 'Use the assistant for everyday actions or summarize text locally without sending it to a cloud service.',
  },
  scheduler: {
    eyebrow: 'Personal planning',
    title: 'Calendar & reminders',
    description: 'Create and manage your events and reminders in one simple workspace.',
  },
  privacy: {
    eyebrow: 'Control center',
    title: 'Privacy & data',
    description: 'Review consent, encryption, identity protection, and what the application actually processes.',
  },
  audit: {
    eyebrow: 'Account history',
    title: 'Audit trail',
    description: 'Inspect the integrity-protected record of actions without mixing it with day-to-day features.',
  },
  federated: {
    eyebrow: 'Advanced workspace',
    title: 'Federated learning',
    description: 'Run dataset preparation, client processes, secure rounds, privacy sweeps, and model export as a separate technical workflow.',
  },
};

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
              <small>private workspace</small>
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
            @if (tab.id === 'federated') {
              <li class="nav-divider" aria-hidden="true"></li>
            }
            <li class="nav-item" role="presentation">
              <button
                type="button"
                class="nav-link"
                [class.active]="activeTab() === tab.id"
                [class.advanced]="tab.id === 'federated'"
                (click)="select(tab.id)"
                [attr.aria-selected]="activeTab() === tab.id"
              >
                <i class="bi" [class]="tabIcon(tab.icon)"></i>
                <span class="tab-copy">
                  <span class="tab-label">{{ tab.label }}</span>
                  <span class="tab-hint">{{ tab.hint }}</span>
                </span>
              </button>
            </li>
          }
        </ul>
      </div>

      <main class="container-fluid px-3 px-lg-4 py-4">
        <div class="page-content">
          <header class="page-heading">
            <div>
              <div class="page-eyebrow">{{ pageMeta[activeTab()].eyebrow }}</div>
              <h1>{{ pageMeta[activeTab()].title }}</h1>
              <p>{{ pageMeta[activeTab()].description }}</p>
            </div>
            @if (activeTab() === 'federated') {
              <div class="page-note">
                <i class="bi bi-diagram-3"></i>
                <span><strong>Advanced tools</strong><br />Separate from your personal assistant data</span>
              </div>
            } @else {
              <div class="page-note quiet">
                <i class="bi bi-shield-check"></i>
                <span><strong>Local-first</strong><br />Your workspace stays focused</span>
              </div>
            }
          </header>

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
        </div>
      </main>

      <footer class="app-footer">
        <span>PPDA · private workspace</span>
        <span class="mono">API connection: relative URL through the app proxy</span>
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
          radial-gradient(900px 420px at 100% 0%, rgba(219, 234, 254, 0.7), transparent 65%),
          radial-gradient(760px 360px at 0% 0%, rgba(224, 231, 255, 0.55), transparent 62%),
          #f5f7fb;
      }
      .app-nav {
        background: rgba(255, 255, 255, 0.96);
        border-bottom: 1px solid #e5e7eb;
        padding: 0.7rem 0;
        backdrop-filter: blur(8px);
      }
      .navbar-brand {
        color: #111827;
        font-weight: 700;
        letter-spacing: 0.02em;
      }
      .brand-icon {
        font-size: 1.35rem;
        color: #2563eb;
      }
      .brand-text {
        display: flex;
        flex-direction: column;
        line-height: 1.1;
      }
      .brand-text small {
        font-size: 0.66rem;
        font-weight: 600;
        color: #64748b;
        letter-spacing: 0.08em;
        text-transform: uppercase;
      }
      .who {
        color: #475569;
        font-size: 0.82rem;
      }
      .uid {
        color: #64748b;
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
        margin-left: 0.25rem;
      }
      .tabs-wrap {
        background: rgba(255, 255, 255, 0.92);
        border-bottom: 1px solid #e5e7eb;
        overflow-x: auto;
      }
      .app-tabs {
        border-bottom: 0;
        flex-wrap: nowrap;
        gap: 0.2rem;
        padding: 0.45rem 0.75rem 0;
        align-items: stretch;
      }
      .app-tabs .nav-link {
        border: 1px solid transparent;
        border-bottom: 3px solid transparent;
        color: #64748b;
        background: transparent;
        border-radius: 0.55rem 0.55rem 0 0;
        display: flex;
        flex-direction: row;
        align-items: center;
        gap: 0.5rem;
        padding: 0.5rem 0.8rem 0.55rem;
        white-space: nowrap;
        text-align: left;
        transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
      }
      .app-tabs .nav-link:hover {
        color: #1f2937;
        background: #f8fafc;
      }
      .app-tabs .nav-link i {
        font-size: 1rem;
        color: #94a3b8;
      }
      .app-tabs .nav-link.active {
        background: #eff6ff;
        border-color: #dbeafe #dbeafe #2563eb;
        color: #1d4ed8;
      }
      .app-tabs .nav-link.active i {
        color: #2563eb;
      }
      .app-tabs .nav-link.advanced {
        color: #6d28d9;
      }
      .app-tabs .nav-link.advanced.active {
        background: #f5f3ff;
        border-color: #ede9fe #ede9fe #7c3aed;
        color: #6d28d9;
      }
      .app-tabs .nav-link.advanced.active i {
        color: #7c3aed;
      }
      .tab-copy {
        display: flex;
        flex-direction: column;
        gap: 0.05rem;
      }
      .tab-label {
        font-size: 0.83rem;
        font-weight: 650;
      }
      .tab-hint {
        font-size: 0.64rem;
        color: #94a3b8;
      }
      .nav-divider {
        width: 1px;
        background: #e5e7eb;
        margin: 0.35rem 0.45rem 0.45rem;
        flex: 0 0 1px;
      }
      main {
        flex: 1 1 auto;
      }
      .page-content {
        width: min(100%, 1480px);
        margin: 0 auto;
      }
      .page-heading {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 1.25rem;
        margin: 0.25rem 0 1.25rem;
      }
      .page-eyebrow {
        color: #2563eb;
        font-size: 0.7rem;
        font-weight: 700;
        letter-spacing: 0.11em;
        text-transform: uppercase;
        margin-bottom: 0.35rem;
      }
      .page-heading h1 {
        color: #111827;
        font-size: clamp(1.45rem, 2.2vw, 2rem);
        font-weight: 720;
        letter-spacing: -0.025em;
        margin: 0;
      }
      .page-heading p {
        color: #64748b;
        font-size: 0.9rem;
        line-height: 1.55;
        max-width: 760px;
        margin: 0.35rem 0 0;
      }
      .page-note {
        display: flex;
        align-items: center;
        gap: 0.55rem;
        flex: 0 0 auto;
        color: #1d4ed8;
        background: rgba(239, 246, 255, 0.9);
        border: 1px solid #dbeafe;
        border-radius: 0.65rem;
        padding: 0.55rem 0.75rem;
        font-size: 0.72rem;
        line-height: 1.35;
      }
      .page-note i {
        font-size: 1.1rem;
      }
      .page-note.quiet {
        color: #475569;
        background: rgba(248, 250, 252, 0.92);
        border-color: #e5e7eb;
      }
      .app-footer {
        border-top: 1px solid #e5e7eb;
        background: rgba(255, 255, 255, 0.72);
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
      @media (max-width: 720px) {
        .page-heading {
          flex-direction: column;
        }
        .page-note {
          align-self: stretch;
        }
        .app-tabs .nav-link {
          padding-inline: 0.65rem;
        }
        .tab-hint {
          display: none;
        }
      }
    `,
  ],
})
export class Shell implements OnDestroy {
  protected readonly auth = inject(AuthService);
  private readonly api = inject(ApiClient);
  private readonly data = inject(DataService);

  readonly tabs = TABS;
  readonly pageMeta = PAGE_META;
  readonly activeTab = signal<TabId>('assistant');
  readonly health = signal<'ok' | 'down'>('down');
  private readonly healthTimer: ReturnType<typeof setInterval>;

  constructor() {
    void this.checkHealth();
    this.healthTimer = setInterval(() => void this.checkHealth(), 15000);
  }

  ngOnDestroy(): void {
    clearInterval(this.healthTimer);
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
