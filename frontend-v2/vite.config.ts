import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import compression from 'vite-plugin-compression';
import path from 'node:path';

// Configuracion Vite del frontend-v2 de UrbIA.
// - Servidor de dev expuesto en LAN (host 0.0.0.0) puerto 3000.
// - Build target es2020, minify terser, chunking manual del vendor.
// - Compresion gzip + brotli sobre los assets emitidos.
export default defineConfig({
  plugins: [
    react(),
    compression({ algorithm: 'gzip', ext: '.gz' }),
    compression({ algorithm: 'brotliCompress', ext: '.br' }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 3000,
    strictPort: true,
    proxy: {
      // En dev, el contenedor del frontend se conecta a la red docker
      // 'urbia-network' (ver scripts/run-frontend-dev). Asi, el nombre
      // de servicio 'backend' resuelve al contenedor FastAPI.
      // En prod, nginx hace el mismo rewrite (ver nginx.conf).
      '/api': {
        target: process.env.VITE_PROXY_TARGET ?? 'http://backend:8000',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
  build: {
    target: 'es2020',
    minify: 'terser',
    sourcemap: false,
    cssCodeSplit: true,
    reportCompressedSize: true,
    chunkSizeWarningLimit: 600,
    terserOptions: {
      compress: { drop_console: true, drop_debugger: true },
    },
    rollupOptions: {
      output: {
        manualChunks: {
          'react-vendor': ['react', 'react-dom', 'react-router-dom'],
          'data-vendor': ['@tanstack/react-query', 'date-fns'],
          'charts': ['recharts'],
          'flow': ['@xyflow/react'],
        },
      },
    },
  },
});
