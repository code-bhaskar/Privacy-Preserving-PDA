import { Component, computed, input } from '@angular/core';

export interface Series {
  label: string;
  color?: string;
  points: number[];
}

const PALETTE = ['#4f8cff', '#22c55e', '#f59e0b', '#ef4444', '#a855f7', '#14b8a6'];

/**
 * Dependency-free SVG chart (HTML5 + inline SVG — no chart library).
 *
 * Two x-axis modes:
 *  - `category`: evenly spaced slots, for accuracy-vs-epsilon (ε = ∞, 10, 5, 1 is
 *    not a linear axis),
 *  - `linear`: x = round index, for accuracy-over-rounds curves.
 */
@Component({
  selector: 'app-sparkline',
  template: `
    @if (hasData()) {
      <div class="chart-wrap">
        <svg
          [attr.viewBox]="viewBox()"
          width="100%"
          [attr.height]="height()"
          role="img"
          [attr.aria-label]="ariaLabel()"
        >
          @for (tick of yTicks(); track tick.value) {
            <line
              [attr.x1]="padLeft"
              [attr.x2]="w - padRight"
              [attr.y1]="tick.y"
              [attr.y2]="tick.y"
              class="grid"
            />
            <text [attr.x]="padLeft - 8" [attr.y]="tick.y + 4" class="axis" text-anchor="end">
              {{ tick.label }}
            </text>
          }

          @for (lab of placedLabels(); track lab.text + lab.x) {
            <text [attr.x]="lab.x" [attr.y]="height() - 7" class="axis" text-anchor="middle">
              {{ lab.text }}
            </text>
          }

          @for (s of plotted(); track s.label) {
            <polyline
              [attr.points]="s.line"
              [attr.stroke]="s.color"
              fill="none"
              stroke-width="2.5"
              stroke-linejoin="round"
              stroke-linecap="round"
            />
            @for (pt of s.dots; track pt.cx + '-' + pt.cy) {
              <circle [attr.cx]="pt.cx" [attr.cy]="pt.cy" r="3.5" [attr.fill]="s.color" />
              <text
                [attr.x]="pt.cx"
                [attr.y]="pt.cy - 9"
                class="value"
                text-anchor="middle"
                [attr.fill]="s.color"
              >
                {{ pt.label }}
              </text>
            }
          }
        </svg>

        <div class="legend">
          @for (s of plotted(); track s.label) {
            <span class="legend-item">
              <i class="dot" [style.background]="s.color"></i>{{ s.label }}
            </span>
          }
        </div>
      </div>
    } @else {
      <div class="empty">No data yet — run a round or a sweep first.</div>
    }
  `,
  styles: [
    `
      .chart-wrap {
        width: 100%;
      }
      svg {
        display: block;
        overflow: visible;
      }
      .grid {
        stroke: rgba(148, 163, 184, 0.22);
        stroke-width: 1;
      }
      .axis {
        fill: #94a3b8;
        font-size: 10px;
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      }
      .value {
        font-size: 10px;
        font-weight: 700;
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      }
      .legend {
        display: flex;
        flex-wrap: wrap;
        gap: 0.75rem;
        margin-top: 0.35rem;
        font-size: 0.75rem;
        color: #cbd5e1;
      }
      .legend-item {
        display: inline-flex;
        align-items: center;
        gap: 0.3rem;
      }
      .dot {
        width: 9px;
        height: 9px;
        border-radius: 50%;
        display: inline-block;
      }
      .empty {
        color: #64748b;
        font-size: 0.85rem;
        padding: 1rem;
        text-align: center;
        border: 1px dashed rgba(148, 163, 184, 0.3);
        border-radius: 0.5rem;
      }
    `,
  ],
})
export class Sparkline {
  readonly series = input<Series[]>([]);
  readonly labels = input<string[]>([]);
  readonly height = input(220);
  readonly yMax = input<number | null>(null);
  readonly mode = input<'category' | 'linear'>('category');
  readonly valueFormat = input<(v: number) => string>((v) => v.toFixed(2));
  readonly ariaLabel = input('chart');

  readonly w = 660;
  readonly padLeft = 44;
  readonly padRight = 16;
  readonly padTop = 16;
  readonly padBottom = 28;

  readonly viewBox = computed(() => `0 0 ${this.w} ${this.height()}`);

  readonly hasData = computed(() => this.series().some((s) => s.points.length > 0));

  private readonly innerW = computed(() => this.w - this.padLeft - this.padRight);
  private readonly innerH = computed(() => this.height() - this.padTop - this.padBottom);

  private readonly maxY = computed(() => {
    const explicit = this.yMax();
    if (explicit !== null && explicit > 0) return explicit;
    const max = Math.max(0.0001, ...this.series().flatMap((s) => s.points));
    return max <= 1 ? 1 : niceCeil(max);
  });

  private readonly count = computed(() => {
    const longest = Math.max(1, ...this.series().map((s) => s.points.length));
    return this.mode() === 'category' ? Math.max(longest, this.labels().length, 1) : longest;
  });

  readonly yTicks = computed(() => {
    const max = this.maxY();
    const h = this.innerH();
    return [0, 0.25, 0.5, 0.75, 1].map((f) => ({
      value: max * f,
      y: this.padTop + h * (1 - f),
      label: formatTick(max * f),
    }));
  });

  private xAt(i: number): number {
    const n = this.count();
    const inner = this.innerW();
    if (n <= 1) return this.padLeft + inner / 2;
    if (this.mode() === 'category') {
      const step = inner / n;
      return this.padLeft + step * (i + 0.5);
    }
    return this.padLeft + (inner * i) / (n - 1);
  }

  private yAt(v: number): number {
    const max = this.maxY() || 1;
    return this.padTop + this.innerH() * (1 - Math.max(0, Math.min(v, max)) / max);
  }

  readonly plotted = computed(() =>
    this.series().map((s, idx) => {
      const color = s.color ?? PALETTE[idx % PALETTE.length];
      const fmt = this.valueFormat();
      const dots = s.points.map((v, i) => ({
        cx: round(this.xAt(i)),
        cy: round(this.yAt(v)),
        label: fmt(v),
      }));
      return { label: s.label, color, dots, line: dots.map((d) => `${d.cx},${d.cy}`).join(' ') };
    }),
  );

  readonly placedLabels = computed(() =>
    this.labels().map((text, i) => ({ text, x: round(this.xAt(i)) })),
  );
}

function round(n: number): number {
  return Math.round(n * 100) / 100;
}

function niceCeil(max: number): number {
  const pow = Math.pow(10, Math.floor(Math.log10(max)));
  return Math.ceil(max / pow) * pow;
}

function formatTick(v: number): string {
  if (v === 0) return '0';
  if (Math.abs(v) >= 1000) return `${(v / 1000).toFixed(v % 1000 === 0 ? 0 : 1)}k`;
  return v.toFixed(v < 1 ? 2 : v < 10 ? 1 : 0);
}
