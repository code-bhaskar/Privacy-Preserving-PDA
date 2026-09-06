import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  AssistantService,
  SAMPLE_COMMANDS,
  SAMPLE_MESSAGES,
} from '../services/assistant.service';
import { AuthService } from '../services/auth.service';
import { DataService } from '../services/data.service';
import { CommandResponse } from '../core/api.types';
import { Pill } from './pill';
import { JsonView } from './json-view';

/**
 * On-device assistant tab.
 *
 * Everything here is produced inside the backend process: ONNX Runtime intent
 * classification, rule-based entity extraction, occlusion-saliency explanation
 * and extractive summarization. Each response reports `processing_location` and
 * whether raw content was ever transmitted externally — both are surfaced as
 * badges so the "0 external calls" claim is visible, not asserted.
 */
@Component({
  selector: 'app-assistant-panel',
  imports: [FormsModule, Pill, JsonView],
  template: `
    <div class="row g-3">
      <div class="col-12 col-xl-7">
        <div class="card panel">
          <div class="card-header panel-head">
            <span><i class="bi bi-chat-dots me-2"></i>Natural-language command</span>
            <app-pill tone="accent" icon="cpu">on-device ONNX intent</app-pill>
          </div>
          <div class="card-body">
            @if (!consentGranted()) {
              <div class="alert alert-warning py-2 small">
                <i class="bi bi-exclamation-triangle-fill me-1"></i>
                Consent category <code>assistant_nlu</code> is not granted, so the backend will
                refuse with <strong>403</strong>. Grant it in the
                <em>Privacy &amp; data</em> tab — that refusal is itself part of the demo.
              </div>
            }

            <form (ngSubmit)="send()" class="d-flex gap-2 mb-3">
              <input
                class="form-control"
                name="command"
                [(ngModel)]="command"
                placeholder="e.g. schedule a meeting with john tomorrow at 10"
                autocomplete="off"
              />
              <button class="btn btn-primary px-3" type="submit" [disabled]="svc.busy()">
                @if (svc.busy()) {
                  <span class="spinner-border spinner-border-sm" aria-hidden="true"></span>
                } @else {
                  <i class="bi bi-send"></i>
                }
              </button>
            </form>

            <details class="sample-prompts mb-3">
              <summary><i class="bi bi-stars me-1"></i>Try a sample command</summary>
              <div class="chips mt-2">
                @for (sample of samples; track sample.intent) {
                  <button
                    type="button"
                    class="chip"
                    (click)="useSample(sample.text)"
                    [title]="'Expected intent: ' + sample.intent"
                  >
                    {{ sample.text }}
                    <em>{{ sample.intent }}</em>
                  </button>
                }
              </div>
            </details>

            <div class="feed">
              @for (line of svc.lines(); track line.id) {
                <div class="line" [class.user]="line.kind === 'user'" [class.err]="line.kind === 'error'">
                  <span class="at">{{ line.at }}</span>
                  <span class="txt">{{ line.text }}</span>
                </div>
              } @empty {
                <p class="muted small mb-0">
                  No commands yet. Pick a chip above — each one exercises a different trained intent.
                </p>
              }
            </div>
          </div>
        </div>
      </div>

      <div class="col-12 col-xl-5">
        <div class="card panel">
          <div class="card-header panel-head">
            <span><i class="bi bi-activity me-2"></i>Latest inference</span>
            @if (last(); as r) {
              <app-pill [tone]="r.processing_location === 'local' ? 'ok' : 'warn'" icon="geo-alt">
                {{ r.processing_location }}
              </app-pill>
            }
          </div>
          <div class="card-body">
            @if (last(); as r) {
              <div class="intent-row">
                <div>
                  <div class="intent">{{ r.intent }}</div>
                  <div class="action">action_taken: <code>{{ r.action_taken }}</code></div>
                </div>
                <div class="text-end">
                  <div class="conf">{{ (r.confidence * 100).toFixed(1) }}%</div>
                  <div class="conf-label">confidence</div>
                </div>
              </div>

              <div class="progress mb-3 conf-bar" role="progressbar"
                   [attr.aria-valuenow]="r.confidence * 100" aria-valuemin="0" aria-valuemax="100">
                <div class="progress-bar" [style.width.%]="r.confidence * 100"></div>
              </div>

              <div class="d-flex flex-wrap gap-2 mb-3">
                <app-pill [tone]="r.requires_ml ? 'info' : 'muted'" icon="cpu">
                  {{ r.requires_ml ? 'ONNX classifier used' : 'no ML needed' }}
                </app-pill>
                <app-pill tone="ok" icon="wifi-off">0 external calls</app-pill>
                @if (r.action_taken === 'confirmation_required') {
                  <app-pill tone="warn" icon="question-circle">destructive action needs an id</app-pill>
                }
              </div>

              <h6 class="sub">Extracted entities</h6>
              <div class="kv mb-3">
                @for (e of entities(r); track e.key) {
                  <div class="kv-row">
                    <span class="k">{{ e.key }}</span>
                    <span class="v">{{ e.value }}</span>
                  </div>
                } @empty {
                  <div class="muted small">none</div>
                }
              </div>

              @if (r.explanation; as ex) {
                <h6 class="sub">
                  Why? <span class="method">{{ ex.method }}</span>
                </h6>
                <div class="saliency mb-3">
                  @for (t of saliency(r); track t.token) {
                    <div class="sal-row" [title]="t.token + ': ' + t.contribution">
                      <span class="tok">{{ t.token }}</span>
                      <span class="bar-track">
                        <span
                          class="bar"
                          [class.neg]="t.contribution < 0"
                          [style.width.%]="barWidth(t.contribution, r)"
                        ></span>
                      </span>
                      <span class="num">{{ t.contribution >= 0 ? '+' : '' }}{{ t.contribution.toFixed(4) }}</span>
                    </div>
                  }
                </div>
                <p class="muted micro">
                  Each bar is the drop in predicted probability when that token is hidden
                  (occlusion). Positive = evidence for <strong>{{ r.intent }}</strong>.
                </p>
              }

              @if (r.result !== null && r.result !== undefined) {
                <h6 class="sub">Result payload</h6>
                <app-json-view [data]="r.result" label="action result" [maxRows]="14" />
              }
            } @else {
              <p class="muted small mb-0">Run a command to see intent, entities and saliency here.</p>
            }
          </div>
        </div>

        <div class="card panel mt-3 summary-panel">
          <div class="card-header panel-head">
            <span><i class="bi bi-text-paragraph me-2"></i>Summarize entered text</span>
            <app-pill tone="ok" icon="wifi-off">local only</app-pill>
          </div>
          <div class="card-body">
            <p class="muted micro mb-2">
              Paste a message, notes, or a conversation below. The extractive summary is built locally;
              it is only persisted when you choose <strong>save securely</strong>.
            </p>
            <label class="form-label small fw-semibold mb-1" for="summaryText">Text to summarize</label>
            <textarea
              id="summaryText"
              name="summaryText"
              class="form-control summary-input"
              rows="6"
              [(ngModel)]="summaryText"
              placeholder="Paste the text you want to summarize…"
            ></textarea>
            <div class="summary-actions mt-2">
              <button class="btn btn-sm btn-link px-0" type="button" (click)="useSampleMessages()">
                <i class="bi bi-stars me-1"></i>Use sample text
              </button>
              <label class="form-label mb-0 small" for="maxSentences">sentences</label>
              <input
                id="maxSentences"
                type="number"
                min="1"
                max="6"
                class="form-control form-control-sm sentence-count"
                [(ngModel)]="maxSentences"
              />
              <div class="form-check form-switch mb-0">
                <input
                  class="form-check-input"
                  type="checkbox"
                  role="switch"
                  id="persist"
                  [(ngModel)]="persist"
                />
                <label class="form-check-label small" for="persist">save securely</label>
              </div>
              <button class="btn btn-sm btn-primary ms-auto" type="button" (click)="summarize()" [disabled]="svc.busy() || !summaryText.trim()">
                <i class="bi bi-magic me-1"></i>Summarize text
              </button>
            </div>
            <details class="input-preview mt-3">
              <summary>Preview {{ messages().length }} message{{ messages().length === 1 ? '' : 's' }} sent to the local summarizer</summary>
              <ol class="msgs mb-0 mt-2">
                @for (m of messages(); track m.sender + m.content) {
                  <li><strong>{{ m.sender }}:</strong> {{ m.content }}</li>
                }
              </ol>
            </details>
            @if (svc.lastSummary(); as s) {
              <div class="summary mt-3">
                <div class="summary-head">
                  <app-pill tone="info" icon="text-left">{{ s.n_messages }} messages</app-pill>
                  <app-pill [tone]="s.raw_content_transmitted_externally ? 'bad' : 'ok'" icon="shield-check">
                    external transmission: {{ s.raw_content_transmitted_externally ? 'YES' : 'none' }}
                  </app-pill>
                </div>
                <p class="mb-0">{{ s.summary }}</p>
              </div>
            }
          </div>
        </div>
      </div>
    </div>
  `,
  styles: [
    `
      .panel {
        background: rgba(255, 255, 255, 0.96);
        border: 1px solid rgba(148, 163, 184, 0.16);
        border-radius: 0.75rem;
      }
      .panel-head {
        background: rgba(248, 250, 252, 0.96);
        border-bottom: 1px solid rgba(148, 163, 184, 0.14);
        color: #1f2937;
        font-size: 0.88rem;
        font-weight: 600;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.5rem;
      }
      .sample-prompts {
        border-top: 1px solid rgba(148, 163, 184, 0.18);
        border-bottom: 1px solid rgba(148, 163, 184, 0.18);
        padding: 0.55rem 0;
      }
      .sample-prompts summary {
        cursor: pointer;
        color: #64748b;
        font-size: 0.78rem;
        font-weight: 600;
        list-style: none;
      }
      .sample-prompts summary::-webkit-details-marker {
        display: none;
      }
      .sample-prompts summary::after {
        content: '+';
        color: #2563eb;
        float: right;
        font-size: 1rem;
        font-weight: 400;
      }
      .sample-prompts[open] summary::after {
        content: '−';
      }
      .chips {
        display: flex;
        flex-wrap: wrap;
        gap: 0.4rem;
      }
      .chip {
        background: rgba(79, 140, 255, 0.08);
        border: 1px solid rgba(79, 140, 255, 0.25);
        color: #64748b;
        border-radius: 999px;
        padding: 0.25rem 0.65rem;
        font-size: 0.74rem;
        display: inline-flex;
        gap: 0.4rem;
        align-items: center;
        transition: background 0.15s ease;
      }
      .chip:hover {
        background: rgba(79, 140, 255, 0.14);
        color: #1d4ed8;
      }
      .chip em {
        font-style: normal;
        font-size: 0.62rem;
        color: #0284c7;
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      }
      .feed {
        background: #f8fafc;
        border: 1px solid rgba(148, 163, 184, 0.16);
        border-radius: 0.5rem;
        padding: 0.6rem 0.75rem;
        max-height: 22rem;
        overflow: auto;
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
        font-size: 0.78rem;
      }
      .line {
        display: flex;
        gap: 0.6rem;
        padding: 0.15rem 0;
        color: #64748b;
      }
      .line .at {
        color: #64748b;
        flex: 0 0 auto;
      }
      .line.user {
        color: #1d4ed8;
      }
      .line.err {
        color: #dc2626;
      }
      .intent-row {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 1rem;
        margin-bottom: 0.5rem;
      }
      .intent {
        font-size: 1.35rem;
        font-weight: 700;
        color: #2563eb;
        letter-spacing: 0.01em;
      }
      .action {
        color: #64748b;
        font-size: 0.76rem;
      }
      .conf {
        font-size: 1.6rem;
        font-weight: 700;
        color: #16a34a;
        line-height: 1;
      }
      .conf-label {
        font-size: 0.66rem;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.08em;
      }
      .conf-bar {
        height: 6px;
        background: rgba(148, 163, 184, 0.15);
      }
      .conf-bar .progress-bar {
        background: linear-gradient(90deg, #4f8cff, #22c55e);
      }
      .sub {
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #64748b;
        margin-bottom: 0.4rem;
      }
      .method {
        text-transform: none;
        letter-spacing: 0;
        color: #64748b;
        font-size: 0.7rem;
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
        color: #0284c7;
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      }
      .kv-row .v {
        color: #1f2937;
        text-align: right;
        word-break: break-word;
      }
      .saliency {
        display: flex;
        flex-direction: column;
        gap: 0.25rem;
      }
      .sal-row {
        display: grid;
        grid-template-columns: 6.5rem 1fr 4.5rem;
        align-items: center;
        gap: 0.5rem;
        font-size: 0.75rem;
      }
      .tok {
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
        color: #64748b;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .bar-track {
        height: 10px;
        background: rgba(148, 163, 184, 0.12);
        border-radius: 999px;
        overflow: hidden;
      }
      .bar {
        display: block;
        height: 100%;
        background: linear-gradient(90deg, #4f8cff, #22c55e);
        border-radius: 999px;
      }
      .bar.neg {
        background: linear-gradient(90deg, #ef4444, #f59e0b);
      }
      .num {
        text-align: right;
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
        color: #64748b;
        font-size: 0.7rem;
      }
      .msgs {
        font-size: 0.8rem;
        color: #64748b;
        padding-left: 1.2rem;
        line-height: 1.6;
      }
      .summary {
        background: rgba(34, 197, 94, 0.07);
        border: 1px solid rgba(34, 197, 94, 0.25);
        border-radius: 0.5rem;
        padding: 0.6rem 0.75rem;
        color: #166534;
        font-size: 0.84rem;
      }
      .summary-head {
        display: flex;
        gap: 0.4rem;
        flex-wrap: wrap;
        margin-bottom: 0.4rem;
      }
      .summary-input {
        min-height: 9rem;
        resize: vertical;
        line-height: 1.55;
      }
      .summary-actions {
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 0.6rem;
      }
      .sentence-count {
        width: 4.25rem;
      }
      .input-preview {
        border-top: 1px solid rgba(148, 163, 184, 0.2);
        padding-top: 0.65rem;
        color: #475569;
        font-size: 0.78rem;
      }
      .input-preview summary {
        cursor: pointer;
        color: #64748b;
        font-weight: 600;
      }
      .input-preview summary:hover {
        color: #2563eb;
      }
      .muted {
        color: #64748b;
      }
      .micro {
        font-size: 0.72rem;
        line-height: 1.5;
      }
      code {
        color: #b45309;
      }
    `,
  ],
})
export class AssistantPanel {
  protected readonly svc = inject(AssistantService);
  private readonly auth = inject(AuthService);
  private readonly data = inject(DataService);

  readonly samples = SAMPLE_COMMANDS;
  command = '';
  maxSentences = 3;
  persist = true;
  summaryText = SAMPLE_MESSAGES.map((m) => `${m.sender}: ${m.content}`).join('\n\n');

  readonly messages = signal(SAMPLE_MESSAGES);

  readonly last = computed<CommandResponse | null>(() => this.svc.lastResponse());
  readonly consentGranted = computed(() => this.auth.consentMap()['assistant_nlu'] === true);

  useSample(text: string): void {
    this.command = text;
    void this.send();
  }

  async send(): Promise<void> {
    const text = this.command.trim();
    if (!text) return;
    this.command = '';
    const res = await this.svc.sendCommand(text);
    // Commands can create/delete calendar rows — keep the scheduler tab in sync.
    if (res && ['event_created', 'reminder_created'].includes(res.action_taken)) {
      await Promise.all([this.data.loadEvents(), this.data.loadReminders()]);
    }
  }

  entities(r: CommandResponse): { key: string; value: string }[] {
    return Object.entries(r.entities ?? {}).map(([key, value]) => ({
      key,
      value: value === null || value === undefined ? '—' : String(value),
    }));
  }

  saliency(r: CommandResponse): { token: string; contribution: number }[] {
    return (r.explanation?.top_tokens ?? []).slice(0, 8);
  }

  barWidth(contribution: number, r: CommandResponse): number {
    const tokens = this.saliency(r);
    const max = Math.max(1e-6, ...tokens.map((t) => Math.abs(t.contribution)));
    return Math.max(2, (Math.abs(contribution) / max) * 100);
  }

  useSampleMessages(): void {
    this.summaryText = SAMPLE_MESSAGES.map((m) => `${m.sender}: ${m.content}`).join('\n\n');
    this.messages.set(SAMPLE_MESSAGES);
  }

  private enteredMessages(): { sender: string; content: string }[] {
    return this.summaryText
      .trim()
      .split(/\n\s*\n/)
      .map((block) => block.trim())
      .filter(Boolean)
      .map((block) => {
        const match = block.match(/^([^:\n]{1,40}):\s*([\s\S]+)$/);
        return match
          ? { sender: match[1].trim(), content: match[2].trim() }
          : { sender: 'You', content: block.replace(/\s+/g, ' ').trim() };
      });
  }

  async summarize(): Promise<void> {
    const entered = this.enteredMessages();
    if (!entered.length) return;
    this.messages.set(entered);
    await this.svc.summarize(entered, this.maxSentences, this.persist);
  }
}
