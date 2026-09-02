import { Component, computed, input, signal } from '@angular/core';

/** Pretty-printed JSON block — the demo shows raw API payloads as evidence. */
@Component({
  selector: 'app-json-view',
  template: `
    <div class="json-head">
      <span class="label">{{ label() }}</span>
      <button type="button" class="btn btn-sm btn-outline-secondary py-0 px-2" (click)="copy()">
        {{ copied() ? 'copied ✓' : 'copy' }}
      </button>
    </div>
    <pre class="json"><code>{{ formatted() }}</code></pre>
  `,
  styles: [
    `
      .json-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.5rem;
        margin-bottom: 0.25rem;
      }
      .label {
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: #94a3b8;
        font-weight: 600;
      }
      .json {
        background: #070b14;
        border: 1px solid rgba(148, 163, 184, 0.18);
        border-radius: 0.5rem;
        padding: 0.6rem 0.75rem;
        margin: 0;
        max-height: 22rem;
        overflow: auto;
        font-size: 0.74rem;
        line-height: 1.45;
        color: #a5f3fc;
        white-space: pre-wrap;
        word-break: break-word;
      }
      button {
        font-size: 0.7rem;
      }
    `,
  ],
})
export class JsonView {
  readonly data = input<unknown>(null);
  readonly label = input('response json');
  readonly maxRows = input<number | null>(null);

  readonly copied = signal(false);

  readonly formatted = computed(() => {
    const value = this.data();
    if (value === null || value === undefined) return '—';
    try {
      const text = JSON.stringify(value, null, 2);
      const rows = this.maxRows();
      if (!rows) return text;
      const lines = text.split('\n');
      return lines.length > rows
        ? `${lines.slice(0, rows).join('\n')}\n… (${lines.length - rows} more lines)`
        : text;
    } catch {
      return String(value);
    }
  });

  copy(): void {
    const text = this.formatted();
    if (navigator.clipboard?.writeText) {
      void navigator.clipboard.writeText(text).catch(() => undefined);
    }
    this.copied.set(true);
    setTimeout(() => this.copied.set(false), 1500);
  }
}
