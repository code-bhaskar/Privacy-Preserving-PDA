import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { ApiClient } from '../core/api-client.service';
import { toApiError } from '../core/auth.interceptor';
import { CalendarEvent, Reminder } from '../core/api.types';

/** `2026-09-05T14:30` — the shape FastAPI/pydantic parses for datetime fields. */
export function toLocalInputValue(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}

export function plusHours(hours: number): string {
  return toLocalInputValue(new Date(Date.now() + hours * 3600_000));
}

/**
 * Calendar + reminder CRUD.
 *
 * Both collections are encrypted at rest on the server (AES-256-GCM with the
 * user id as AAD); the plaintext you see here is what the API decrypts for the
 * authenticated owner only.
 */
@Injectable({ providedIn: 'root' })
export class DataService {
  private readonly api = inject(ApiClient);

  readonly events = signal<CalendarEvent[]>([]);
  readonly reminders = signal<Reminder[]>([]);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);

  async loadEvents(): Promise<CalendarEvent[]> {
    this.loading.set(true);
    try {
      const events = await firstValueFrom(this.api.get<CalendarEvent[]>('/events'));
      this.events.set(events.sort((a, b) => a.start_time.localeCompare(b.start_time)));
      return events;
    } catch (err) {
      this.error.set(toApiError(err).message);
      return [];
    } finally {
      this.loading.set(false);
    }
  }

  async createEvent(title: string, start: string, end: string | null, participant: string | null): Promise<CalendarEvent | null> {
    try {
      const created = await firstValueFrom(
        this.api.post<CalendarEvent>('/events', {
          title,
          start_time: start,
          end_time: end || null,
          participant: participant || null,
        }),
      );
      this.events.update((list) => [...list, created]);
      this.error.set(null);
      return created;
    } catch (err) {
      this.error.set(toApiError(err).message);
      return null;
    }
  }

  async updateEvent(id: number, patch: Partial<CalendarEvent>): Promise<CalendarEvent | null> {
    try {
      const updated = await firstValueFrom(this.api.put<CalendarEvent>(`/events/${id}`, patch));
      this.events.update((list) => list.map((e) => (e.id === id ? updated : e)));
      this.error.set(null);
      return updated;
    } catch (err) {
      this.error.set(toApiError(err).message);
      return null;
    }
  }

  async deleteEvent(id: number): Promise<boolean> {
    try {
      await firstValueFrom(this.api.delete(`/events/${id}`));
      this.events.update((list) => list.filter((e) => e.id !== id));
      this.error.set(null);
      return true;
    } catch (err) {
      this.error.set(toApiError(err).message);
      return false;
    }
  }

  async loadReminders(): Promise<Reminder[]> {
    this.loading.set(true);
    try {
      const reminders = await firstValueFrom(this.api.get<Reminder[]>('/reminders'));
      this.reminders.set(reminders.sort((a, b) => a.due_time.localeCompare(b.due_time)));
      return reminders;
    } catch (err) {
      this.error.set(toApiError(err).message);
      return [];
    } finally {
      this.loading.set(false);
    }
  }

  async createReminder(text: string, dueTime: string): Promise<Reminder | null> {
    try {
      const created = await firstValueFrom(
        this.api.post<Reminder>('/reminders', { text, due_time: dueTime }),
      );
      this.reminders.update((list) => [...list, created]);
      this.error.set(null);
      return created;
    } catch (err) {
      this.error.set(toApiError(err).message);
      return null;
    }
  }

  async updateReminder(id: number, patch: Partial<Reminder>): Promise<Reminder | null> {
    try {
      const updated = await firstValueFrom(this.api.put<Reminder>(`/reminders/${id}`, patch));
      this.reminders.update((list) => list.map((r) => (r.id === id ? updated : r)));
      this.error.set(null);
      return updated;
    } catch (err) {
      this.error.set(toApiError(err).message);
      return null;
    }
  }

  async deleteReminder(id: number): Promise<boolean> {
    try {
      await firstValueFrom(this.api.delete(`/reminders/${id}`));
      this.reminders.update((list) => list.filter((r) => r.id !== id));
      this.error.set(null);
      return true;
    } catch (err) {
      this.error.set(toApiError(err).message);
      return false;
    }
  }

  clear(): void {
    this.events.set([]);
    this.reminders.set([]);
    this.error.set(null);
  }
}
