import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { ApiClient } from '../core/api-client.service';
import { toApiError } from '../core/auth.interceptor';
import { CommandResponse, SummarizeResponse } from '../core/api.types';

export interface ChatLine {
  id: number;
  kind: 'user' | 'assistant' | 'error' | 'info';
  text: string;
  at: string;
  response?: CommandResponse;
}

/**
 * One command per trained intent class. The wording is taken from the training
 * corpus (app/Data_sets/intent/intent_seed.py) so the demo hits high-confidence
 * predictions instead of an unlucky edge case live on stage.
 */
export const SAMPLE_COMMANDS: { text: string; intent: string }[] = [
  { text: 'schedule a meeting with john tomorrow at 10', intent: 'SCHEDULE_EVENT' },
  { text: 'remind me to submit the report tomorrow at 6', intent: 'CREATE_REMINDER' },
  { text: 'show my agenda for next week', intent: 'GET_EVENTS' },
  { text: 'list all my pending reminders', intent: 'GET_REMINDERS' },
  { text: 'cancel my meeting with john', intent: 'DELETE_EVENT' },
  { text: 'remove the medicine reminder', intent: 'DELETE_REMINDER' },
  { text: 'summarize my messages', intent: 'SUMMARIZE_MESSAGES' },
  { text: 'hello how are you', intent: 'GREETING' },
];

export const SAMPLE_MESSAGES = [
  {
    sender: 'Priya',
    content:
      'Can we move the budget review to Thursday 11am? I need the finance numbers first.',
  },
  {
    sender: 'Tom',
    content:
      'The vendor contract is signed. Delivery slips two weeks, so the demo moves to the 24th.',
  },
  {
    sender: 'Aisha',
    content:
      'Reminder: security audit checklist is due Friday. Encryption-at-rest evidence is still missing.',
  },
  {
    sender: 'Priya',
    content: 'Also book the small meeting room, not the open area. Thanks!',
  },
];

/**
 * On-device assistant: intent classification (ONNX Runtime), entity extraction,
 * occlusion-saliency explainability and local extractive summarization.
 * Every call reports `processing_location` and whether anything left the device.
 */
@Injectable({ providedIn: 'root' })
export class AssistantService {
  private readonly api = inject(ApiClient);

  readonly lines = signal<ChatLine[]>([]);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly lastResponse = signal<CommandResponse | null>(null);
  readonly lastSummary = signal<SummarizeResponse | null>(null);

  private seq = 0;

  private push(line: Omit<ChatLine, 'id' | 'at'>): void {
    this.lines.update((list) => [
      ...list,
      { ...line, id: ++this.seq, at: new Date().toLocaleTimeString() },
    ]);
  }

  say(text: string, kind: ChatLine['kind'] = 'info', response?: CommandResponse): void {
    this.push({ kind, text, response });
  }

  reset(): void {
    this.lines.set([]);
    this.lastResponse.set(null);
    this.lastSummary.set(null);
    this.error.set(null);
  }

  async sendCommand(text: string): Promise<CommandResponse | null> {
    if (!text.trim()) return null;
    this.busy.set(true);
    this.error.set(null);
    this.push({ kind: 'user', text });
    try {
      const res = await firstValueFrom(
        this.api.post<CommandResponse>('/assistant/command', { text }),
      );
      this.lastResponse.set(res);
      this.push({
        kind: 'assistant',
        text: `${res.intent} · ${(res.confidence * 100).toFixed(1)}% · ${res.action_taken}`,
        response: res,
      });
      return res;
    } catch (err) {
      const e = toApiError(err);
      this.error.set(e.message);
      this.push({ kind: 'error', text: e.message });
      return null;
    } finally {
      this.busy.set(false);
    }
  }

  async summarize(
    messages: { sender: string; content: string }[],
    maxSentences = 3,
    persist = true,
  ): Promise<SummarizeResponse | null> {
    this.busy.set(true);
    this.error.set(null);
    try {
      const res = await firstValueFrom(
        this.api.post<SummarizeResponse>('/messages/summarize', {
          messages,
          max_sentences: maxSentences,
          persist,
        }),
      );
      this.lastSummary.set(res);
      this.push({
        kind: 'assistant',
        text: `Summary of ${res.n_messages} messages (${res.processing_location}, ` +
          `external transmission: ${res.raw_content_transmitted_externally ? 'YES' : 'no'})`,
      });
      return res;
    } catch (err) {
      const e = toApiError(err);
      this.error.set(e.message);
      this.push({ kind: 'error', text: e.message });
      return null;
    } finally {
      this.busy.set(false);
    }
  }
}
