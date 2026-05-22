// Role-based default landing — ADR 0042. The map lives in code so a
// reviewer reading the diff sees the routing decision in the same PR
// as the screen it accompanies.

import 'server-only';

// Keycloak realm-role names (see infra/keycloak/realm-sbs-demo.json).
export const ROLE_SUPERVISOR = 'sbs:conduct:supervisor';
export const ROLE_ANALYST = 'sbs:conduct:analyst';
export const ROLE_HEAD = 'sbs:conduct:head';

// Order matters — first match wins (ADR 0042 D2). Production may grow
// segment-level overrides; for the demo the rule is the workflow each
// role starts their day on.
const PRECEDENCE: readonly { role: string; route: string }[] = [
  { role: ROLE_HEAD, route: '/approvals' },
  { role: ROLE_ANALYST, route: '/findings' },
  { role: ROLE_SUPERVISOR, route: '/cockpit' },
];

const FALLBACK_ROUTE = '/cockpit';

/**
 * Resolve the landing route for a set of granted roles.
 *
 * Returns a path WITHOUT the basePath prefix; the caller composes the
 * final URL. Returns the fallback (cockpit) if no precedence rule
 * matches the granted roles.
 */
export function landingRouteForRoles(roles: readonly string[]): string {
  for (const { role, route } of PRECEDENCE) {
    if (roles.includes(role)) return route;
  }
  return FALLBACK_ROUTE;
}
