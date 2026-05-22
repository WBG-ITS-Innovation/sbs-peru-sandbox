// OAuth + Keycloak configuration. Sourced from environment variables;
// no hardcoded secrets. See ../../../.env.example for the full set.

import 'server-only';

function required(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(
      `Missing required environment variable: ${name}. ` +
        `See app/.env.example. Production overlays set this via Helm secret.`,
    );
  }
  return value;
}

function optional(name: string, fallback: string): string {
  return process.env[name] ?? fallback;
}

export const authConfig = {
  // Keycloak base URL (the externally-reachable origin). Defaults to the
  // docker-compose-mapped port for local development.
  keycloakBaseUrl: optional('KEYCLOAK_BASE_URL', 'http://localhost:8081'),
  // Realm and client id come from infra/keycloak/realm-sbs-demo.json.
  // Same names in production; the underlying realm definition changes.
  realm: optional('KEYCLOAK_REALM', 'sbs-demo'),
  clientId: optional('KEYCLOAK_CLIENT_ID', 'sbs-supervisor-ui'),
  // The redirect URI registered with Keycloak. basePath is /app, so the
  // route handler lives at /app/api/auth/callback.
  redirectUri: optional(
    'KEYCLOAK_REDIRECT_URI',
    'http://localhost:3000/app/api/auth/callback',
  ),
  // After logout, Keycloak sends the user back here.
  postLogoutRedirectUri: optional(
    'KEYCLOAK_POST_LOGOUT_REDIRECT_URI',
    'http://localhost:3000/app/login',
  ),

  // Shared secret used to authenticate the Next.js server when it calls
  // FastAPI's /v1/internal/* endpoints (the cross-screen audit chain).
  // Required at runtime; throws on missing rather than silently failing
  // the audit write.
  internalApiSecret: required.bind(null, 'SBS_INTERNAL_API_SECRET'),
  // Base URL of the FastAPI service the Next.js server calls for audit
  // writes (and, later, server-side data fetches). Different from the
  // browser-facing URL because Next.js calls FastAPI server-to-server.
  internalApiBaseUrl: optional('SBS_INTERNAL_API_BASE_URL', 'http://localhost:8000'),

  // Demo-mode flag — gates the persona switcher. Off in production.
  demoMode: process.env.SBS_DEMO_MODE === 'true',
};

export const oidcEndpoints = {
  authorize: () =>
    `${authConfig.keycloakBaseUrl}/realms/${authConfig.realm}/protocol/openid-connect/auth`,
  token: () =>
    `${authConfig.keycloakBaseUrl}/realms/${authConfig.realm}/protocol/openid-connect/token`,
  logout: () =>
    `${authConfig.keycloakBaseUrl}/realms/${authConfig.realm}/protocol/openid-connect/logout`,
  userinfo: () =>
    `${authConfig.keycloakBaseUrl}/realms/${authConfig.realm}/protocol/openid-connect/userinfo`,
} as const;
