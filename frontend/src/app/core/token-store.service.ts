import { Injectable, signal } from '@angular/core';

const STORAGE_KEY = 'ppda.jwt';

/**
 * Minimal holder for the JWT bearer token.
 *
 * It is separate from AuthService so the HTTP interceptor can read the token
 * without creating a circular dependency (AuthService -> ApiClient -> interceptor).
 */
@Injectable({ providedIn: 'root' })
export class TokenStore {
  private readonly _token = signal<string | null>(this.read());

  readonly token = this._token.asReadonly();

  get(): string | null {
    return this._token();
  }

  set(token: string | null): void {
    if (token) {
      try {
        localStorage.setItem(STORAGE_KEY, token);
      } catch {
        /* private mode / storage blocked — the session still works in memory */
      }
    } else {
      try {
        localStorage.removeItem(STORAGE_KEY);
      } catch {
        /* ignore */
      }
    }
    this._token.set(token);
  }

  clear(): void {
    this.set(null);
  }

  private read(): string | null {
    try {
      return localStorage.getItem(STORAGE_KEY);
    } catch {
      return null;
    }
  }
}
