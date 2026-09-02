import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DataService, plusHours } from '../services/data.service';
import { AuthService } from '../services/auth.service';
import { CalendarEvent, Reminder } from '../core/api.types';
import { Pill } from './pill';

/**
 * Calendar & reminders CRUD.
 *
 * The plaintext in this tab exists only in the HTTP response: the rows in
 * `calendar_events.title` and `reminders.text` are AES-256-GCM ciphertext bound
 * to the owner's user id as AAD, and no request body carries a user_id — the
 * backend derives it from the JWT.
 */
@Component({
  selector: 'app-scheduler-panel',
  imports: [FormsModule, Pill],
  template: `
    @if (!consentGranted()) {
      <div class="alert alert-warning py-2 small">
        <i class="bi bi-exclamation-triangle-fill me-1"></i>
        Consent category <code>calendar_data</code> is not granted — create/read calls will be
        refused with <strong>403</strong>. Toggle it in the <em>Privacy &amp; data</em> tab.
      </div>
    }

    <div class="row g-3">
      <div class="col-12 col-xl-7">
        <div class="card panel">
          <div class="card-header panel-head">
            <span><i class="bi bi-calendar3 me-2"></i>Calendar events</span>
            <div class="d-flex gap-2">
              <app-pill tone="ok" icon="lock">AES-256-GCM at rest</app-pill>
              <button class="btn btn-sm btn-outline-light" (click)="reload()" [disabled]="svc.loading()">
                <i class="bi bi-arrow-clockwise"></i>
              </button>
            </div>
          </div>
          <div class="card-body">
            <form (ngSubmit)="createEvent()" class="row g-2 mb-3">
              <div class="col-12 col-md-5">
                <input
                  class="form-control form-control-sm"
                  name="evTitle"
                  [(ngModel)]="evTitle"
                  placeholder="Title (encrypted on the server)"
                  required
                />
              </div>
              <div class="col-6 col-md-3">
                <input
                  class="form-control form-control-sm"
                  type="datetime-local"
                  name="evStart"
                  [(ngModel)]="evStart"
                  required
                />
              </div>
              <div class="col-6 col-md-2">
                <input
                  class="form-control form-control-sm"
                  type="datetime-local"
                  name="evEnd"
                  [(ngModel)]="evEnd"
                  placeholder="end"
                />
              </div>
              <div class="col-8 col-md-2">
                <input
                  class="form-control form-control-sm"
                  name="evWho"
                  [(ngModel)]="evWho"
                  placeholder="participant"
                />
              </div>
              <div class="col-4 col-md-2 d-grid">
                <button class="btn btn-sm btn-primary" type="submit">
                  <i class="bi bi-plus-lg me-1"></i>Add
                </button>
              </div>
            </form>

            <div class="table-responsive">
              <table class="table table-sm align-middle data">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Title</th>
                    <th>Start</th>
                    <th>End</th>
                    <th>Participant</th>
                    <th>Via</th>
                    <th class="text-end">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  @for (e of events(); track e.id) {
                    <tr [class.editing]="editingEvent() === e.id">
                      <td class="mono dim">{{ e.id }}</td>
                      <td>
                        @if (editingEvent() === e.id) {
                          <input class="form-control form-control-sm" [(ngModel)]="editTitle" />
                        } @else {
                          <span class="title">{{ e.title }}</span>
                        }
                      </td>
                      <td class="mono small">{{ fmt(e.start_time) }}</td>
                      <td class="mono small dim">{{ fmt(e.end_time) }}</td>
                      <td class="small">{{ e.participant ?? '—' }}</td>
                      <td>
                        <app-pill [tone]="e.created_via === 'assistant' ? 'accent' : 'muted'">
                          {{ e.created_via }}
                        </app-pill>
                      </td>
                      <td class="text-end">
                        @if (editingEvent() === e.id) {
                          <button class="btn btn-sm btn-success me-1" (click)="saveEvent(e)">
                            <i class="bi bi-check-lg"></i>
                          </button>
                          <button class="btn btn-sm btn-outline-secondary" (click)="cancelEdit()">
                            <i class="bi bi-x-lg"></i>
                          </button>
                        } @else {
                          <button class="btn btn-sm btn-outline-light me-1" (click)="startEdit(e)">
                            <i class="bi bi-pencil"></i>
                          </button>
                          <button class="btn btn-sm btn-outline-danger" (click)="removeEvent(e.id)">
                            <i class="bi bi-trash"></i>
                          </button>
                        }
                      </td>
                    </tr>
                  } @empty {
                    <tr>
                      <td colspan="7" class="muted small py-3 text-center">
                        No events yet — add one above, or say “schedule a meeting with john tomorrow at 10”
                        in the Assistant tab.
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      <div class="col-12 col-xl-5">
        <div class="card panel">
          <div class="card-header panel-head">
            <span><i class="bi bi-bell me-2"></i>Reminders</span>
            <app-pill tone="info" icon="clock-history">scheduler fires due items</app-pill>
          </div>
          <div class="card-body">
            <form (ngSubmit)="createReminder()" class="row g-2 mb-3">
              <div class="col-12 col-md-7">
                <input
                  class="form-control form-control-sm"
                  name="rmText"
                  [(ngModel)]="rmText"
                  placeholder="Reminder text (encrypted)"
                  required
                />
              </div>
              <div class="col-8 col-md-3">
                <input
                  class="form-control form-control-sm"
                  type="datetime-local"
                  name="rmDue"
                  [(ngModel)]="rmDue"
                  required
                />
              </div>
              <div class="col-4 col-md-2 d-grid">
                <button class="btn btn-sm btn-primary" type="submit">
                  <i class="bi bi-plus-lg me-1"></i>Add
                </button>
              </div>
            </form>

            <ul class="reminder-list">
              @for (r of reminders(); track r.id) {
                <li [class.done]="r.status !== 'pending'">
                  <div class="r-main">
                    @if (editingReminder() === r.id) {
                      <input class="form-control form-control-sm" [(ngModel)]="editRmText" />
                    } @else {
                      <span class="r-text">{{ r.text }}</span>
                    }
                    <span class="r-meta">
                      <i class="bi bi-clock me-1"></i>{{ fmt(r.due_time) }}
                      <app-pill [tone]="r.status === 'pending' ? 'warn' : 'ok'" class="ms-2">
                        {{ r.status }}
                      </app-pill>
                    </span>
                  </div>
                  <div class="r-actions">
                    @if (editingReminder() === r.id) {
                      <button class="btn btn-sm btn-success" (click)="saveReminder(r)">
                        <i class="bi bi-check-lg"></i>
                      </button>
                      <button class="btn btn-sm btn-outline-secondary" (click)="cancelRmEdit()">
                        <i class="bi bi-x-lg"></i>
                      </button>
                    } @else {
                      @if (r.status === 'pending') {
                        <button class="btn btn-sm btn-outline-success" (click)="complete(r)" title="Mark done">
                          <i class="bi bi-check2-circle"></i>
                        </button>
                      }
                      <button class="btn btn-sm btn-outline-light" (click)="startRmEdit(r)">
                        <i class="bi bi-pencil"></i>
                      </button>
                      <button class="btn btn-sm btn-outline-danger" (click)="removeReminder(r.id)">
                        <i class="bi bi-trash"></i>
                      </button>
                    }
                  </div>
                </li>
              } @empty {
                <li class="muted small py-3 text-center border-0">
                  No reminders yet.
                </li>
              }
            </ul>
          </div>
        </div>

        <div class="card panel mt-3">
          <div class="card-header panel-head">
            <span><i class="bi bi-info-circle me-2"></i>What the server actually stores</span>
          </div>
          <div class="card-body">
            <p class="muted micro mb-2">
              Every row you just created is written as AES-256-GCM ciphertext with your user id as
              Authenticated Additional Data, and audit reasons never contain the plaintext.
            </p>
            <pre class="sql"><code>SELECT id, title FROM calendar_events LIMIT 2;
-- 1 | xBrZpLWjU/RrHUF2ek6CZB8tnFkNUeZJ5KIO1I7g6kXznHc=
--   ↑ AES-256-GCM ciphertext, not "Budget review with finance"</code></pre>
            <p class="muted micro mb-0 mt-2">
              Run that against the live database during the demo — or check the
              <em>Audit trail</em> tab, where the reason column stays plaintext-free.
            </p>
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
        font-weight: 600;
      }
      table.data td {
        border-bottom: 1px solid rgba(148, 163, 184, 0.08);
        vertical-align: middle;
      }
      tr.editing {
        background: rgba(79, 140, 255, 0.08);
      }
      .title {
        color: #f1f5f9;
        font-weight: 500;
      }
      .mono {
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      }
      .dim {
        color: #64748b;
      }
      .reminder-list {
        list-style: none;
        padding: 0;
        margin: 0;
        display: flex;
        flex-direction: column;
        gap: 0.4rem;
      }
      .reminder-list li {
        display: flex;
        justify-content: space-between;
        gap: 0.6rem;
        align-items: center;
        background: rgba(7, 11, 20, 0.7);
        border: 1px solid rgba(148, 163, 184, 0.14);
        border-radius: 0.5rem;
        padding: 0.45rem 0.6rem;
      }
      .reminder-list li.done .r-text {
        color: #64748b;
        text-decoration: line-through;
      }
      .r-main {
        display: flex;
        flex-direction: column;
        gap: 0.15rem;
        min-width: 0;
      }
      .r-text {
        color: #e2e8f0;
        font-size: 0.84rem;
        word-break: break-word;
      }
      .r-meta {
        color: #7c8aa0;
        font-size: 0.7rem;
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
        display: flex;
        align-items: center;
        gap: 0.2rem;
      }
      .r-actions {
        display: flex;
        gap: 0.25rem;
        flex: 0 0 auto;
      }
      .sql {
        background: #070b14;
        border: 1px solid rgba(148, 163, 184, 0.18);
        border-radius: 0.5rem;
        padding: 0.55rem 0.7rem;
        margin: 0;
        color: #a5f3fc;
        font-size: 0.72rem;
        overflow: auto;
      }
      .muted {
        color: #7c8aa0;
      }
      .micro {
        font-size: 0.74rem;
        line-height: 1.5;
      }
      code {
        color: #fbbf24;
      }
    `,
  ],
})
export class SchedulerPanel {
  protected readonly svc = inject(DataService);
  private readonly auth = inject(AuthService);

  evTitle = '';
  evStart = plusHours(24);
  evEnd = plusHours(25);
  evWho = '';

  rmText = '';
  rmDue = plusHours(3);

  readonly editingEvent = signal<number | null>(null);
  editTitle = '';
  readonly editingReminder = signal<number | null>(null);
  editRmText = '';

  readonly events = computed(() => this.svc.events());
  readonly reminders = computed(() => this.svc.reminders());
  readonly consentGranted = computed(() => this.auth.consentMap()['calendar_data'] === true);

  constructor() {
    void this.reload();
  }

  async reload(): Promise<void> {
    await Promise.all([this.svc.loadEvents(), this.svc.loadReminders()]);
  }

  fmt(value: string | null): string {
    if (!value) return '—';
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return value;
    return d.toLocaleString(undefined, {
      month: 'short',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  async createEvent(): Promise<void> {
    if (!this.evTitle.trim()) return;
    const created = await this.svc.createEvent(
      this.evTitle.trim(),
      this.evStart,
      this.evEnd || null,
      this.evWho.trim() || null,
    );
    if (created) {
      this.evTitle = '';
      this.evWho = '';
      this.evStart = plusHours(24);
      this.evEnd = plusHours(25);
      await this.svc.loadEvents();
    }
  }

  startEdit(e: CalendarEvent): void {
    this.editingEvent.set(e.id);
    this.editTitle = e.title;
  }

  cancelEdit(): void {
    this.editingEvent.set(null);
  }

  async saveEvent(e: CalendarEvent): Promise<void> {
    const updated = await this.svc.updateEvent(e.id, { title: this.editTitle.trim() });
    if (updated) this.editingEvent.set(null);
  }

  async removeEvent(id: number): Promise<void> {
    await this.svc.deleteEvent(id);
  }

  async createReminder(): Promise<void> {
    if (!this.rmText.trim()) return;
    const created = await this.svc.createReminder(this.rmText.trim(), this.rmDue);
    if (created) {
      this.rmText = '';
      this.rmDue = plusHours(3);
      await this.svc.loadReminders();
    }
  }

  startRmEdit(r: Reminder): void {
    this.editingReminder.set(r.id);
    this.editRmText = r.text;
  }

  cancelRmEdit(): void {
    this.editingReminder.set(null);
  }

  async saveReminder(r: Reminder): Promise<void> {
    const updated = await this.svc.updateReminder(r.id, { text: this.editRmText.trim() });
    if (updated) this.editingReminder.set(null);
  }

  async complete(r: Reminder): Promise<void> {
    // app/models/reminder.py documents the lifecycle as pending|done|fired
    await this.svc.updateReminder(r.id, { status: 'done' });
  }

  async removeReminder(id: number): Promise<void> {
    await this.svc.deleteReminder(id);
  }
}
