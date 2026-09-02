import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { ApiClient } from '../core/api-client.service';
import { toApiError } from '../core/auth.interceptor';
import { AuditRecord, AuditVerifyResult } from '../core/api.types';

/**
 * Tamper-evident audit trail.
 *
 * Each row stores `prev_hash` -> `integrity_hash` (SHA-256 chain), and the
 * database has append-only triggers that reject UPDATE/DELETE on `audit_logs`.
 * `GET /audit/verify` re-walks the chain from genesis.
 */
@Injectable({ providedIn: 'root' })
export class AuditService {
  private readonly api = inject(ApiClient);

  readonly records = signal<AuditRecord[]>([]);
  readonly verification = signal<AuditVerifyResult | null>(null);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);

  async load(limit = 200): Promise<AuditRecord[]> {
    this.busy.set(true);
    try {
      const records = await firstValueFrom(this.api.get<AuditRecord[]>('/audit', { limit }));
      this.records.set(records);
      this.error.set(null);
      return records;
    } catch (err) {
      this.error.set(toApiError(err).message);
      return [];
    } finally {
      this.busy.set(false);
    }
  }

  async verify(): Promise<AuditVerifyResult | null> {
    this.busy.set(true);
    try {
      const result = await firstValueFrom(this.api.get<AuditVerifyResult>('/audit/verify'));
      this.verification.set(result);
      this.error.set(null);
      return result;
    } catch (err) {
      this.error.set(toApiError(err).message);
      return null;
    } finally {
      this.busy.set(false);
    }
  }

  /** Chain walk rendered in the UI: does each row really point at its predecessor? */
  chainChecks(): { id: number; ok: boolean; why: string }[] {
    const rows = [...this.records()].sort((a, b) => a.id - b.id);
    return rows.map((row, i) => {
      const prev = i === 0 ? null : rows[i - 1];
      if (i === 0) {
        return {
          id: row.id,
          ok: !row.prev_hash || row.prev_hash === '' || row.prev_hash.startsWith('0'),
          why: 'genesis record (no predecessor)',
        };
      }
      const ok = row.prev_hash === prev?.integrity_hash;
      return {
        id: row.id,
        ok,
        why: ok
          ? 'prev_hash matches the previous integrity_hash'
          : `prev_hash ${shortHash(row.prev_hash)} != previous ${shortHash(prev?.integrity_hash)}`,
      };
    });
  }

  reset(): void {
    this.records.set([]);
    this.verification.set(null);
    this.error.set(null);
  }
}

export function shortHash(hash: string | null | undefined, size = 12): string {
  if (!hash) return '—';
  return hash.length > size ? `${hash.slice(0, size)}…` : hash;
}
