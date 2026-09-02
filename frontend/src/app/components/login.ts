import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';
import { AuthService } from '../services/auth.service';
import { DataService, plusHours } from '../services/data.service';
import { ApiClient } from '../core/api-client.service';
import { Pill } from './pill';

export const DEMO_EMAIL = 'demo@ppda.io';
export const DEMO_PASSWORD = 'DemoPass123!';

/**
 * Login / register screen.
 *
 * "Load demo" is the one-click path used during the presentation: it registers
 * (or reuses) a demo account, logs in for a JWT, grants all four consent
 * categories and seeds a couple of encrypted records so every tab has content.
 */
@Component({
  selector: 'app-login',
  imports: [FormsModule, Pill],
  template: `
    <div class="login-shell">
      <div class="login-card card shadow-lg">
        <div class="card-body p-4 p-md-5">
          <div class="brand mb-4">
            <div class="brand-mark"><i class="bi bi-shield-lock-fill"></i></div>
            <div>
              <h1 class="h4 mb-0">Privacy-Preserving Digital Assistant</h1>
              <p class="subtitle mb-0">
                Local-first assistant · JWT auth · AES-256-GCM at rest · ONNX on-device intent ·
                tamper-evident audit · Bonawitz secure aggregation
              </p>
            </div>
          </div>

          <div class="d-flex flex-wrap gap-2 mb-4">
            <app-pill [tone]="health() === 'ok' ? 'ok' : 'bad'" [icon]="health() === 'ok' ? 'plug-fill' : 'plug-fill'">
              backend {{ health() === 'ok' ? 'reachable' : 'unreachable' }}
            </app-pill>
            <app-pill tone="info" icon="database">SQLite / PostgreSQL 18</app-pill>
            <app-pill tone="accent" icon="cpu">ONNX Runtime</app-pill>
          </div>

          <ul class="nav nav-pills mb-3" role="tablist">
            <li class="nav-item">
              <button
                type="button"
                class="nav-link"
                [class.active]="mode() === 'login'"
                (click)="setMode('login')"
              >
                <i class="bi bi-box-arrow-in-right me-1"></i>Sign in
              </button>
            </li>
            <li class="nav-item">
              <button
                type="button"
                class="nav-link"
                [class.active]="mode() === 'register'"
                (click)="setMode('register')"
              >
                <i class="bi bi-person-plus me-1"></i>Register
              </button>
            </li>
          </ul>

          <form (ngSubmit)="submit()" class="needs-validation" novalidate>
            @if (mode() === 'register') {
              <div class="mb-3">
                <label class="form-label" for="name">Name</label>
                <input
                  id="name"
                  name="name"
                  class="form-control"
                  [(ngModel)]="name"
                  placeholder="Sai Sujith"
                  autocomplete="name"
                  required
                />
              </div>
            }
            <div class="mb-3">
              <label class="form-label" for="email">Email</label>
              <input
                id="email"
                name="email"
                type="email"
                class="form-control"
                [(ngModel)]="email"
                placeholder="you@example.com"
                autocomplete="email"
                required
              />
              <div class="form-text">
                The API logs in by email and derives your identity from the signed JWT only.
              </div>
            </div>
            <div class="mb-3">
              <label class="form-label" for="password">Password</label>
              <div class="input-group">
                <input
                  id="password"
                  name="password"
                  [type]="showPassword() ? 'text' : 'password'"
                  class="form-control"
                  [(ngModel)]="password"
                  placeholder="••••••••"
                  autocomplete="current-password"
                  required
                />
                <button
                  type="button"
                  class="btn btn-outline-secondary"
                  (click)="showPassword.set(!showPassword())"
                  [attr.aria-label]="showPassword() ? 'Hide password' : 'Show password'"
                >
                  <i class="bi" [class.bi-eye]="!showPassword()" [class.bi-eye-slash]="showPassword()"></i>
                </button>
              </div>
              <div class="form-text">
                Stored as a bcrypt hash (72-byte truncation applied). 5 failed logins →
                HTTP 429 for 5 minutes.
              </div>
            </div>

            @if (error()) {
              <div class="alert alert-danger py-2 px-3 small" role="alert">
                <i class="bi bi-exclamation-triangle-fill me-1"></i>{{ error() }}
              </div>
            }
            @if (notice()) {
              <div class="alert alert-info py-2 px-3 small" role="status">
                <i class="bi bi-info-circle-fill me-1"></i>{{ notice() }}
              </div>
            }

            <div class="d-grid gap-2">
              <button type="submit" class="btn btn-primary btn-lg" [disabled]="busy()">
                @if (busy()) {
                  <span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>
                }
                {{ mode() === 'login' ? 'Sign in' : 'Create account & sign in' }}
              </button>
              <button
                type="button"
                class="btn btn-outline-success"
                (click)="loadDemo()"
                [disabled]="busy()"
              >
                <i class="bi bi-magic me-1"></i>
                {{ demoBusy() ? demoStep() : 'Load demo (register + consent + seed data)' }}
              </button>
            </div>
          </form>

          <hr class="my-4" />
          <p class="hint mb-0">
            <i class="bi bi-lightbulb me-1"></i>
            New users start with <strong>no consent granted</strong>. The assistant, summarizer and
            federated round endpoints answer <code>403</code> until the matching category is granted —
            that gate is part of the demo (Privacy &amp; Data tab).
          </p>
        </div>
      </div>
    </div>
  `,
  styles: [
    `
      .login-shell {
        min-height: 100vh;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 2rem 1rem;
        background:
          radial-gradient(1200px 600px at 15% -10%, rgba(79, 140, 255, 0.22), transparent 60%),
          radial-gradient(900px 500px at 110% 10%, rgba(139, 92, 246, 0.18), transparent 55%),
          #070b14;
      }
      .login-card {
        width: 100%;
        max-width: 44rem;
        background: rgba(13, 20, 34, 0.92);
        border: 1px solid rgba(148, 163, 184, 0.18);
        border-radius: 1rem;
        backdrop-filter: blur(6px);
      }
      .brand {
        display: flex;
        gap: 1rem;
        align-items: flex-start;
      }
      .brand-mark {
        flex: 0 0 auto;
        width: 3rem;
        height: 3rem;
        border-radius: 0.9rem;
        display: grid;
        place-items: center;
        font-size: 1.5rem;
        color: #bfdbfe;
        background: linear-gradient(145deg, rgba(79, 140, 255, 0.35), rgba(139, 92, 246, 0.3));
        border: 1px solid rgba(147, 197, 253, 0.35);
      }
      .subtitle {
        color: #94a3b8;
        font-size: 0.82rem;
        line-height: 1.5;
        margin-top: 0.25rem;
      }
      .hint {
        color: #94a3b8;
        font-size: 0.8rem;
        line-height: 1.55;
      }
      code {
        color: #fbbf24;
      }
      :host ::ng-deep .form-control {
        background: #0b1220;
        border-color: rgba(148, 163, 184, 0.28);
        color: #e2e8f0;
      }
      :host ::ng-deep .form-control:focus {
        background: #0b1220;
        border-color: #4f8cff;
        box-shadow: 0 0 0 0.2rem rgba(79, 140, 255, 0.18);
        color: #f8fafc;
      }
      :host ::ng-deep .form-label {
        color: #cbd5e1;
        font-size: 0.82rem;
        font-weight: 600;
      }
      :host ::ng-deep .form-text {
        color: #7c8aa0;
        font-size: 0.72rem;
      }
      :host ::ng-deep .nav-pills .nav-link {
        color: #94a3b8;
        font-size: 0.85rem;
      }
      :host ::ng-deep .nav-pills .nav-link.active {
        background: #4f8cff;
        color: #fff;
      }
      hr {
        border-color: rgba(148, 163, 184, 0.18);
      }
    `,
  ],
})
export class Login {
  private readonly auth = inject(AuthService);
  private readonly api = inject(ApiClient);
  private readonly data = inject(DataService);

  readonly mode = signal<'login' | 'register'>('login');
  readonly showPassword = signal(false);
  readonly busy = signal(false);
  readonly demoBusy = signal(false);
  readonly demoStep = signal('');
  readonly health = signal<'ok' | 'down'>('down');

  name = 'Demo User';
  email = DEMO_EMAIL;
  password = DEMO_PASSWORD;

  readonly error = computed(() => this.auth.error());
  readonly notice = signal<string | null>(null);

  constructor() {
    void this.pingHealth();
  }

  private async pingHealth(): Promise<void> {
    try {
      const res = await firstValueFrom(this.api.health());
      this.health.set(res?.status === 'ok' ? 'ok' : 'down');
    } catch {
      this.health.set('down');
    }
  }

  setMode(mode: 'login' | 'register'): void {
    this.mode.set(mode);
    this.auth.clearError();
    this.notice.set(null);
  }

  async submit(): Promise<void> {
    if (!this.email || !this.password) {
      this.notice.set('Email and password are required.');
      return;
    }
    this.busy.set(true);
    this.notice.set(null);
    try {
      if (this.mode() === 'register') {
        await this.auth.register(this.name || 'Demo User', this.email, this.password);
        this.notice.set('Account created — signing in…');
      }
      await this.auth.login(this.email, this.password);
      await this.data.loadEvents();
      await this.data.loadReminders();
    } catch {
      /* AuthService already surfaced the message */
    } finally {
      this.busy.set(false);
    }
  }

  /** One-click demo bootstrap used during the presentation. */
  async loadDemo(): Promise<void> {
    this.demoBusy.set(true);
    this.notice.set(null);
    this.auth.clearError();
    try {
      this.demoStep.set('Signing in…');
      try {
        await this.auth.login(DEMO_EMAIL, DEMO_PASSWORD);
      } catch {
        this.demoStep.set('Registering demo user…');
        await this.auth.register('Demo User', DEMO_EMAIL, DEMO_PASSWORD);
        await this.auth.login(DEMO_EMAIL, DEMO_PASSWORD);
      }

      this.demoStep.set('Granting consent…');
      await this.auth.grantAllConsents();

      this.demoStep.set('Seeding encrypted records…');
      await this.seed();

      this.demoStep.set('Loading calendar & reminders…');
      await Promise.all([this.data.loadEvents(), this.data.loadReminders()]);
    } catch (err) {
      this.notice.set(`Demo bootstrap failed: ${(err as Error).message}`);
    } finally {
      this.demoBusy.set(false);
      this.demoStep.set('');
    }
  }

  private async seed(): Promise<void> {
    const events = this.data.events();
    if (events.length === 0) {
      await this.data.createEvent(
        'Budget review with finance',
        plusHours(26),
        plusHours(27.5),
        'Priya',
      );
      await this.data.createEvent('Vendor security audit walkthrough', plusHours(50), plusHours(51), 'Aisha');
    }
    const reminders = this.data.reminders();
    if (reminders.length === 0) {
      await this.data.createReminder('Submit the compliance checklist', plusHours(20));
      await this.data.createReminder('Call the client about delivery slip', plusHours(4));
    }
  }
}
