import type { Config } from 'tailwindcss';

// WS1 (design system) defines the SBS palette, typography scale, and
// severity tokens. This file holds the bare minimum so the build does
// not error — the actual theme lives in WS1.
const config: Config = {
  content: ['./src/**/*.{ts,tsx}'],
  theme: {
    extend: {},
  },
  plugins: [],
};

export default config;
