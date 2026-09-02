/**
 * The demo frontend always talks to the backend through a RELATIVE base URL.
 *
 *  - `ng serve` uses proxy.conf.json to forward /api, /health and /docs to
 *    http://127.0.0.1:8000, so the browser only ever sees one origin (no CORS,
 *    no hard-coded localhost from the browser).
 *  - a production build served by any static server that proxies /api works the
 *    same way.
 */
export const environment = {
  production: false,
  apiBase: '/api/v1',
  healthUrl: '/health',
  docsUrl: '/docs',
  /** How often the federated pipeline tab polls the coordinator (ms). */
  flPollMs: 1500,
};
