import type { Config } from 'tailwindcss';

// SBS visual design system — ADR 0041. Every colour token here is the
// semantic name; the literal palette lives in app/src/app/globals.css
// as CSS custom properties. Components reference the semantic names
// (bg-severity-critical, text-fg-primary, ring-focus); a palette tweak
// at Luis's review touches globals.css once and propagates.

const config: Config = {
  content: ['./src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Brand
        brand: {
          navy: 'var(--color-brand-navy)',
          cyan: 'var(--color-brand-cyan)',
          gold: 'var(--color-brand-gold)',
        },
        // Surfaces
        surface: {
          DEFAULT: 'var(--color-surface)',
          subtle: 'var(--color-surface-subtle)',
          elevated: 'var(--color-surface-elevated)',
          inverted: 'var(--color-surface-inverted)',
        },
        // Foreground
        fg: {
          DEFAULT: 'var(--color-fg)',
          muted: 'var(--color-fg-muted)',
          subtle: 'var(--color-fg-subtle)',
          inverted: 'var(--color-fg-inverted)',
          link: 'var(--color-fg-link)',
        },
        // Borders
        border: {
          DEFAULT: 'var(--color-border)',
          strong: 'var(--color-border-strong)',
          subtle: 'var(--color-border-subtle)',
        },
        // Severity (semantic — D2 of ADR 0041)
        severity: {
          'low-bg': 'var(--severity-low-bg)',
          'low-fg': 'var(--severity-low-fg)',
          'low-border': 'var(--severity-low-border)',
          'medium-bg': 'var(--severity-medium-bg)',
          'medium-fg': 'var(--severity-medium-fg)',
          'medium-border': 'var(--severity-medium-border)',
          'high-bg': 'var(--severity-high-bg)',
          'high-fg': 'var(--severity-high-fg)',
          'high-border': 'var(--severity-high-border)',
          'critical-bg': 'var(--severity-critical-bg)',
          'critical-fg': 'var(--severity-critical-fg)',
          'critical-border': 'var(--severity-critical-border)',
        },
        // Status (resolution states)
        status: {
          'pending-bg': 'var(--status-pending-bg)',
          'pending-fg': 'var(--status-pending-fg)',
          'in-review-bg': 'var(--status-in-review-bg)',
          'in-review-fg': 'var(--status-in-review-fg)',
          'resolved-bg': 'var(--status-resolved-bg)',
          'resolved-fg': 'var(--status-resolved-fg)',
          'escalated-bg': 'var(--status-escalated-bg)',
          'escalated-fg': 'var(--status-escalated-fg)',
        },
        // Interaction
        accent: {
          DEFAULT: 'var(--color-accent)',
          fg: 'var(--color-accent-fg)',
          hover: 'var(--color-accent-hover)',
        },
        focus: 'var(--focus-ring)',
        danger: {
          DEFAULT: 'var(--color-danger)',
          fg: 'var(--color-danger-fg)',
        },
      },
      fontFamily: {
        sans: ['var(--font-sans)', 'system-ui', 'sans-serif'],
        mono: ['var(--font-mono)', 'ui-monospace', 'monospace'],
      },
      fontSize: {
        // D5 type scale from the v2.1 prompt
        '2xs': ['11px', { lineHeight: '14px' }],
        xs: ['12px', { lineHeight: '16px' }],
        sm: ['13px', { lineHeight: '18px' }],
        base: ['14px', { lineHeight: '20px' }],
        lg: ['16px', { lineHeight: '24px' }],
        xl: ['18px', { lineHeight: '26px' }],
        '2xl': ['22px', { lineHeight: '30px' }],
        '3xl': ['28px', { lineHeight: '36px' }],
        '4xl': ['36px', { lineHeight: '44px' }],
      },
      borderRadius: {
        // ADR 0041 D5: 2px on tables and similar — "deliberate, not retro"
        sbs: '2px',
      },
      keyframes: {
        'fade-in': {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
        'slide-up': {
          from: { transform: 'translateY(8px)', opacity: '0' },
          to: { transform: 'translateY(0)', opacity: '1' },
        },
      },
      animation: {
        'fade-in': 'fade-in 150ms ease-out',
        'slide-up': 'slide-up 200ms ease-out',
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
};

export default config;
