import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

type Params = Record<string, string | number | boolean | undefined | null>;

/**
 * Single place every backend call goes through.
 *
 * URLs are RELATIVE (`/api/v1/...`) so the Angular dev-server proxy forwards them
 * to FastAPI. The browser never dials localhost:8000 itself, which keeps the demo
 * working behind a reverse proxy / preview host without any code change.
 */
@Injectable({ providedIn: 'root' })
export class ApiClient {
  private readonly http = inject(HttpClient);

  readonly base = environment.apiBase;

  /** Last error message, for the global status strip. */
  readonly lastError = signal<string | null>(null);

  get<T>(path: string, params?: Params): Observable<T> {
    return this.http.get<T>(this.url(path), { params: this.toParams(params) });
  }

  post<T>(path: string, body: unknown = {}, params?: Params): Observable<T> {
    return this.http.post<T>(this.url(path), body, { params: this.toParams(params) });
  }

  put<T>(path: string, body: unknown = {}): Observable<T> {
    return this.http.put<T>(this.url(path), body);
  }

  delete<T>(path: string): Observable<T> {
    return this.http.delete<T>(this.url(path));
  }

  /** Raw call to a non-/api path (used for `GET /health`). */
  getAbsolute<T>(url: string): Observable<T> {
    return this.http.get<T>(url);
  }

  health(): Observable<{ status: string; app: string }> {
    return this.getAbsolute<{ status: string; app: string }>(environment.healthUrl);
  }

  noteError(message: string | null): void {
    this.lastError.set(message);
  }

  private url(path: string): string {
    return path.startsWith('/') ? `${this.base}${path}` : `${this.base}/${path}`;
  }

  private toParams(params?: Params): HttpParams {
    let p = new HttpParams();
    if (!params) return p;
    for (const [key, value] of Object.entries(params)) {
      if (value === undefined || value === null) continue;
      p = p.set(key, String(value));
    }
    return p;
  }
}
