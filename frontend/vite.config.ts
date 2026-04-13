import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';
import { sseLoggerPlugin } from './vite-plugin-sse-logger';

export default defineConfig({
  plugins: [react(), sseLoggerPlugin()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
      '@mock': path.resolve(__dirname, 'docs/mock'),
    },
  },
  server: {
    port: 5173,
    host: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'react-vendor': ['react', 'react-dom', 'react-router-dom'],
          'antd-vendor': ['antd', '@ant-design/icons'],
          'echarts-vendor': ['echarts', 'echarts-for-react'],
          'markdown-vendor': ['react-markdown', 'remark-gfm'],
        },
      },
    },
    chunkSizeWarningLimit: 800,
  },
});
