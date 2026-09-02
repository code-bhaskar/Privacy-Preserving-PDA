import { HttpErrorResponse, HttpEvent, HttpHandlerFn, HttpRequest } from '@angular/common/http';
import { inject } from '@angular/core';
import { Observable, throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { TokenStore } from './token-store.service';

/** Normalised error the UI renders in its alert banners. */
export class ApiError {
  constructor(
    readonly status: number,
    readonly message: string,
    readonly detail: unknown = null,
  ) {}

  toString(): string {
    return this.status ? `HTTP ${this.status} — ${this.message}` : this.message;
  }
}

/** Turns any HTTP failure into an ApiError with the backend's own `detail` text. */
export function toApiError(err: unknown): ApiError {
  if (err instanceof ApiError) return err;
  if (err instanceof HttpErrorResponse) {
    const body = err.error as { detail?: unknown } | null;
    let message = err.statusText || 'Request failed';
    const detail = body?.detail;
    if (typeof detail === 'string') {
      message = detail;
    } else if (Array.isArray(detail) && detail.length) {
      const first = detail[0] as { msg?: string; loc?: unknown[] };
      message = `${first?.msg ?? 'Validation error'}${
        first?.loc ? ` (${[...first.loc].slice(1).join('.')})` : ''
      }`;
    } else if (detail) {
      message = JSON.stringify(detail);
    }
    if (err.status === 0) {
      message = 'Cannot reach the backend. Is uvicorn running on port 8000?';
    }
    return new ApiError(err.status, message, detail ?? null);
  }
  if (err instanceof Error) return new ApiError(0, err.message);
  return new ApiError(0, String(err));
}

/**
 * Functional interceptor (Angular 20 style):
 *  - attaches `Authorization: Bearer <jwt>` to /api calls,
 *  - normalises every failure into an ApiError.
 */
export function authInterceptor(req: HttpRequest<unknown>, next: HttpHandlerFn): Observable<HttpEvent<unknown>> {
  const tokens = inject(TokenStore);
  const token = tokens.get();

  let request = req;
  if (token && req.url.startsWith('/api')) {
    request = req.clone({ setHeaders: { Authorization: `Bearer ${token}` } });
  }

  return next(request).pipe(catchError((err) => throwError(() => toApiError(err))));
}
