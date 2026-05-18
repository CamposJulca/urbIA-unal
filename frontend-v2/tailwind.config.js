import tailwindcssAnimate from 'tailwindcss-animate';

/** @type {import('tailwindcss').Config} */
// Tailwind + tokens institucionales UNAL para UrbIA frontend-v2.
// Paleta principal: azul UNAL (#1A3A6E) + amarillo (#FFC107) de acento.
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    container: {
      center: true,
      padding: '1.5rem',
      screens: { '2xl': '1280px' },
    },
    extend: {
      colors: {
        primary: {
          DEFAULT: '#1A3A6E',
          dark: '#122846',
          light: '#2E5A9E',
          foreground: '#FFFFFF',
        },
        accent: {
          DEFAULT: '#FFC107',
          foreground: '#0F172A',
        },
        success: { DEFAULT: '#10B981', foreground: '#FFFFFF' },
        warning: { DEFAULT: '#F59E0B', foreground: '#0F172A' },
        danger: { DEFAULT: '#EF4444', foreground: '#FFFFFF' },
        bg: { DEFAULT: '#F8FAFC' },
        surface: { DEFAULT: '#FFFFFF' },
        ink: {
          DEFAULT: '#0F172A',
          muted: '#64748B',
          subtle: '#94A3B8',
        },
        border: { DEFAULT: '#E2E8F0' },
        neutral: {
          50: '#F8FAFC',
          100: '#F1F5F9',
          200: '#E2E8F0',
          300: '#CBD5E1',
          400: '#94A3B8',
          500: '#64748B',
          600: '#475569',
          700: '#334155',
          800: '#1E293B',
          900: '#0F172A',
        },
      },
      fontFamily: {
        display: ['Inter', 'system-ui', 'sans-serif'],
        body: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      borderRadius: {
        lg: '0.75rem',
        md: '0.5rem',
        sm: '0.25rem',
      },
      boxShadow: {
        card: '0 1px 2px rgba(15, 23, 42, 0.04), 0 1px 3px rgba(15, 23, 42, 0.06)',
        elev: '0 10px 25px -10px rgba(15, 23, 42, 0.18), 0 4px 10px -4px rgba(15, 23, 42, 0.12)',
      },
      keyframes: {
        'pulse-soft': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.55' },
        },
        'pulse-slow': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.4' },
        },
        flash: {
          '0%': { backgroundColor: 'rgba(255, 193, 7, 0.35)' },
          '100%': { backgroundColor: 'transparent' },
        },
        dash: { to: { strokeDashoffset: '-20' } },
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        'slide-up': {
          '0%': { opacity: '0', transform: 'translateY(12px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        loader: {
          '0%': { transform: 'translateX(-100%)' },
          '100%': { transform: 'translateX(300%)' },
        },
      },
      animation: {
        'pulse-soft': 'pulse-soft 2s ease-in-out infinite',
        'pulse-slow': 'pulse-slow 3.5s ease-in-out infinite',
        flash: 'flash 1s ease-out',
        dash: 'dash 0.6s linear infinite',
        'fade-in': 'fade-in 0.4s ease-out both',
        'slide-up': 'slide-up 0.5s ease-out both',
        loader: 'loader 1.2s ease-in-out infinite',
      },
    },
  },
  plugins: [tailwindcssAnimate],
};
