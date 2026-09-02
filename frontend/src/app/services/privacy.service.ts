import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { ApiClient } from '../core/api-client.service';
import { toApiError } from '../core/auth.interceptor';
import { EncryptDemoResult, PrivacyPosture } from '../core/api.types';

export interface IdrorProbe {
  targetUserId: number;
  status: number;
  detail: string;
  verdict: 'safe' | 'leak';
  note: string;
  at: string;
}

/**
 * The "privacy evidence" panel: encryption-at-rest round trip, the honest
 * implemented-vs-architecture-only posture map, and IDOR probes.
 */
@Injectable({ providedIn: 'root' })
export class PrivacyService {
  private readonly api = inject(ApiClient);

  readonly posture = signal<PrivacyPosture[]>([]);
  readonly encryptResult = signal<EncryptDemoResult | null>(null);
  readonly encryptInput = signal<string | null>(null);
  readonly probes = signal<IdrorProbe[]>([]);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);

  async loadPosture(): Promise<PrivacyPosture[]> {
    try {
      const posture = await firstValueFrom(this.api.get<PrivacyPosture[]>('/privacy/posture'));
      this.posture.set(posture);
      return posture;
    } catch (err) {
      this.error.set(toApiError(err).message);
      return [];
    }
  }

  async encryptDemo(plaintext: string): Promise<EncryptDemoResult | null> {
    this.busy.set(true);
    this.error.set(null);
    try {
      const res = await firstValueFrom(
        this.api.post<EncryptDemoResult>('/privacy/encrypt-demo', { plaintext }),
      );
      this.encryptResult.set(res);
      this.encryptInput.set(plaintext);
      return res;
    } catch (err) {
      this.error.set(toApiError(err).message);
      return null;
    } finally {
      this.busy.set(false);
    }
  }

  /**
   * Ask for another user's record and show the raw HTTP status.
   * 404 = correct (existence is not disclosed); 200/403 = a finding.
   */
  async probeUser(otherId: number): Promise<IdrorProbe | null> {
    this.busy.set(true);
    this.error.set(null);
    try {
      let status = 200;
      let detail = '';
      try {
        const res = await firstValueFrom(this.api.get(`/users/${otherId}`));
        detail = `LEAK — the API returned another user's record: ${JSON.stringify(res)}`;
      } catch (err) {
        const e = toApiError(err);
        status = e.status;
        detail = e.message;
      }
      const probe: IdrorProbe = {
        targetUserId: otherId,
        status,
        detail,
        verdict: status === 404 ? 'safe' : 'leak',
        note:
          status === 404
            ? 'Correct: 404 Not Found, not 403 Forbidden — object existence is never disclosed.'
            : status === 403
              ? 'Finding: 403 confirms the object exists. The backend is designed to answer 404.'
              : 'Finding: unexpected status — inspect the response above.',
        at: new Date().toLocaleTimeString(),
      };
      this.probes.update((list) => [probe, ...list].slice(0, 12));
      return probe;
    } finally {
      this.busy.set(false);
    }
  }

  reset(): void {
    this.posture.set([]);
    this.encryptResult.set(null);
    this.encryptInput.set(null);
    this.probes.set([]);
    this.error.set(null);
  }
}
