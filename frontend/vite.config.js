import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.js',
    // Leaflet needs a real browser layout engine; the map is covered by the
    // Playwright smoke test instead of here.
    exclude: ['**/node_modules/**', '**/dist/**', '**/*.e2e.*'],
  },
});
