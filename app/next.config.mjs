/** @type {import('next').NextConfig} */

// The supervisor UI is served at /app/ in production (behind the FastAPI
// reverse proxy that already serves /v1/portal/). In development the
// Next.js dev server runs standalone on :3000 but still under /app/ so
// the URL shape matches production from day one.
const nextConfig = {
  basePath: '/app',
  reactStrictMode: true,
  poweredByHeader: false,
  async redirects() {
    return [
      {
        source: '/',
        destination: '/app/api/auth/demo-login',
        permanent: false,
        basePath: false,
      },
    ];
  },
  experimental: {
    // App Router is GA in Next 14; this block stays empty until we need
    // anything that genuinely experimental.
  },
};

export default nextConfig;
