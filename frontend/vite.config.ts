import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { env } from 'node:process';
// Server-only override for an isolated local demo; never exposed in the browser bundle.
const apiTarget = env.RECRUITFLOW_API_TARGET || 'http://127.0.0.1:8000';
const target = new URL(apiTarget);
if (target.protocol !== 'http:' || !['127.0.0.1', 'localhost', '[::1]'].includes(target.hostname) || target.username || target.password || target.pathname !== '/' || target.search || target.hash) {
  throw new Error('RECRUITFLOW_API_TARGET must be a local HTTP origin');
}
export default defineConfig({
  plugins: [react()],
  server: { host: '127.0.0.1', port: 5173, strictPort: true, proxy: { '/api': apiTarget } },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return;
          if (/\/(react|react-dom|scheduler|react-router|react-router-dom)\//.test(id)) return 'framework';
          if (id.includes('/zrender/')) return 'chart-renderer';
          if (id.includes('/echarts/')) return 'chart-engine';
          if (id.includes('/@ant-design/icons')) return 'icons';
          if (id.includes('/@ant-design/cssinjs') || id.includes('/@emotion/') || id.includes('/stylis/')) return 'ui-styles';
        },
      },
    },
  },
});
