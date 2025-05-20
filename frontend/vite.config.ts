import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

const root = resolve(__dirname, 'src');

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@assets': resolve(root, 'assets'),
      '@components': resolve(root, 'components'),
      '@lib': resolve(root, 'lib'),
      '@styles': resolve(root, 'styles'),
      '@types': resolve(root, 'types/index.ts'),
      '@pages': resolve(root, 'pages'),
    },
  },
  css: {
    preprocessorOptions: {
      scss: {
        api: 'modern',
      },
    },
  }
})
