import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';

const root = resolve(__dirname, 'src');

export default defineConfig({
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
  plugins: [react()],
  resolve: {
    alias: {
      '@components': resolve(root, 'components'),
      '@styles': resolve(root, 'styles'),
      '@pages': resolve(root, 'pages'),
      '@contexts': resolve(root, 'contexts'),
      '@utils': resolve(root, 'utils'),
      '@hooks': resolve(root, 'hooks'),
      '@api': resolve(root, 'api'),
    },
  },
  css: {
    preprocessorOptions: {
      scss: {
        api: 'modern',
      },
    },
  },
});
