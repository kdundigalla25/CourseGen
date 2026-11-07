import { defineConfig } from 'vitest/config';
import { loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  server: { proxy: { '/api': loadEnv(mode, '.', '').COURSE_PLANNER_API_TARGET || 'http://127.0.0.1:8000' } },
  test: { exclude: ['e2e/**','node_modules/**'] },
}));
