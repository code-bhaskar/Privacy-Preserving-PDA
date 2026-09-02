import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { ApiClient } from '../core/api-client.service';
import { toApiError } from '../core/auth.interceptor';
import { TokenStore } from '../core/token-store.service';
import { Consent, ConsentCategory, Token, User } from '../core/api.types';

export const CONSENT_CATEGORIES: { key: ConsentCategory; label: string; hint: string }[] = [
  {
    key: 'assistant_nlu',
    label: 'Assistant NLU',
    hint: 'On-device intent classification + entity extraction for natural-language commands.',
  },
  {
    key: 'calendar_data',
    label: 'Calendar data',
    hint: 'Create, read and update calendar events (titles encrypted at rest).',
  },
  {
    key: 'message_summarization',
    label: 'Message summarization',
    hint: 'Local extractive summarization — no message content ever leaves the process.',
  },
  {
    key: 'federated_training',
    label: 'Federated training',
    hint: 'Contribute masked model updates to a secure-aggregation round.',
  },
];

/**
 * Registration / login / logout / "who am I" / consent.
 *
 * The JWT is the only identity the UI holds: every other request is scoped by the
 * backend from the token (the API has no client-supplied user_id anywhere), which
 * is the IDOR defence the demo shows off.
 */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly api = inject(ApiClient);
  private readonly tokens = inject(TokenStore);

  readonly user = signal<User | null>(null);
  readonly consents = signal<Consent[]>([]);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);

  readonly isAuthenticated = computed(() => this.user() !== null);
  readonly hasToken = computed(() => this.tokens.token() !== null);

  readonly consentMap = computed<Record<string, boolean>>(() => {
    const map: Record<string, boolean> = {};
    for (const c of this.consents()) map[c.category] = c.granted;
    return map;
  });

  constructor() {
    // A token from a previous session: re-validate it instead of forcing re-login.
    if (this.tokens.get()) {
      void this.loadMe();
    }
  }

  token(): string | null {
    return this.tokens.get();
  }

  async register(name: string, email: string, password: string): Promise<User> {
    this.loading.set(true);
    this.error.set(null);
    try {
      const user = await firstValueFrom(
        this.api.post<User>('/users', { name, email, password, preferences: {} }),
      );
      return user;
    } catch (err) {
      const e = toApiError(err);
      this.error.set(e.message);
      throw e;
    } finally {
      this.loading.set(false);
    }
  }

  async login(email: string, password: string): Promise<User> {
    this.loading.set(true);
    this.error.set(null);
    try {
      const token = await firstValueFrom(
        this.api.post<Token>('/login', { email, password }),
      );
      this.tokens.set(token.access_token);
      const me = await firstValueFrom(this.api.get<User>('/users/me'));
      this.user.set(me);
      await this.refreshConsents();
      return me;
    } catch (err) {
      const e = toApiError(err);
      this.tokens.clear();
      this.user.set(null);
      this.error.set(e.status === 429 ? `${e.message} (brute-force rate limit)` : e.message);
      throw e;
    } finally {
      this.loading.set(false);
    }
  }

  async logout(): Promise<void> {
    try {
      if (this.tokens.get()) {
        await firstValueFrom(this.api.post<{ message: string }>('/logout'));
      }
    } catch {
      /* the token is dropped locally either way — revocation is best effort here */
    } finally {
      this.tokens.clear();
      this.user.set(null);
      this.consents.set([]);
    }
  }

  async loadMe(): Promise<User | null> {
    try {
      const me = await firstValueFrom(this.api.get<User>('/users/me'));
      this.user.set(me);
      await this.refreshConsents();
      return me;
    } catch {
      this.tokens.clear();
      this.user.set(null);
      return null;
    }
  }

  async refreshConsents(): Promise<Consent[]> {
    try {
      const consents = await firstValueFrom(this.api.get<Consent[]>('/consent'));
      this.consents.set(consents);
      return consents;
    } catch (err) {
      this.error.set(toApiError(err).message);
      return [];
    }
  }

  async setConsent(category: ConsentCategory, granted: boolean): Promise<Consent> {
    try {
      const consent = await firstValueFrom(
        this.api.post<Consent>('/consent', { category, granted }),
      );
      this.consents.update((list) => {
        const rest = list.filter((c) => c.category !== category);
        return [...rest, consent];
      });
      return consent;
    } catch (err) {
      const e = toApiError(err);
      this.error.set(e.message);
      throw e;
    }
  }

  async grantAllConsents(): Promise<void> {
    for (const c of CONSENT_CATEGORIES) {
      await this.setConsent(c.key, true);
    }
  }

  /**
   * IDOR probe: ask for somebody else's record.
   * A correct backend answers 404 (never 403), so existence is not leaked.
   */
  async probeOtherUser(otherId: number): Promise<{ status: number; detail: string }> {
    try {
      const res = await firstValueFrom(this.api.get<User>(`/users/${otherId}`));
      return { status: 200, detail: `LEAK — got a user back: ${JSON.stringify(res)}` };
    } catch (err) {
      const e = toApiError(err);
      return { status: e.status, detail: e.message };
    }
  }

  clearError(): void {
    this.error.set(null);
  }
}
