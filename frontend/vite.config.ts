import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({
  plugins: [react()],
  server: { host: '127.0.0.1', port: 5173, strictPort: true, proxy: { '/api': 'http://127.0.0.1:8000' } },
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
