import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'node:path';

// Config separada para vitest — no contamina vite.config.ts ni el
// pipeline de build de produccion. Reusa el plugin react y el alias '@'.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    include: ['src/**/*.test.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      include: ['src/lib/**', 'src/api/**', 'src/components/ui/**'],
      exclude: ['**/*.test.{ts,tsx}', '**/index.ts'],
    },
  },
});
