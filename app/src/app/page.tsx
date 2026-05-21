import { redirect } from 'next/navigation';

// The root of the supervisor app (/app/) redirects to /app/cockpit by
// default. Role-based landing (supervisor → cockpit, analyst → findings,
// head → approvals) lands in the OAuth commit alongside the session
// inspection — until then, everyone reaches the cockpit. See ADR 0042
// (role-based default landing).
export default function RootPage() {
  redirect('/cockpit');
}
