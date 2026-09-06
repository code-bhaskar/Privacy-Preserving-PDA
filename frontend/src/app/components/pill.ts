import { Component, input } from '@angular/core';

/**
 * Small status chip. `tone` maps to Bootstrap-flavoured colours used across the
 * demo (implemented / refused / masked / broken …).
 */
@Component({
  selector: 'app-pill',
  template: `<span class="pill" [class]="tone()" [attr.title]="title()">
    @if (icon()) {
      <i class="bi" [class]="iconClass()"></i>
    }
    <ng-content></ng-content>
  </span>`,
  styles: [
    `
      .pill {
        display: inline-flex;
        align-items: center;
        gap: 0.3rem;
        padding: 0.15rem 0.5rem;
        border-radius: 999px;
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 0.01em;
        border: 1px solid transparent;
        white-space: nowrap;
      }
      .ok {
        color: #16a34a;
        background: rgba(34, 197, 94, 0.12);
        border-color: rgba(34, 197, 94, 0.35);
      }
      .info {
        color: #0284c7;
        background: rgba(56, 189, 248, 0.12);
        border-color: rgba(56, 189, 248, 0.35);
      }
      .warn {
        color: #b45309;
        background: rgba(245, 158, 11, 0.12);
        border-color: rgba(245, 158, 11, 0.35);
      }
      .bad {
        color: #dc2626;
        background: rgba(239, 68, 68, 0.12);
        border-color: rgba(239, 68, 68, 0.35);
      }
      .muted {
        color: #64748b;
        background: rgba(148, 163, 184, 0.1);
        border-color: rgba(148, 163, 184, 0.28);
      }
      .accent {
        color: #7c3aed;
        background: rgba(139, 92, 246, 0.14);
        border-color: rgba(139, 92, 246, 0.35);
      }
      .bi {
        font-size: 0.75rem;
      }
    `,
  ],
})
export class Pill {
  readonly tone = input<'ok' | 'info' | 'warn' | 'bad' | 'muted' | 'accent'>('muted');
  readonly icon = input<string>('');
  readonly title = input<string>('');

  iconClass(): string {
    return `bi-${this.icon()}`;
  }
}
