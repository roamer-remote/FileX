import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react-swc'
import { resolve } from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true,
      },
    },
  },
  test: {
    environment: 'node',
    setupFiles: ['./src/test/setupDom.ts'],
    environmentMatchGlobs: [['**/*.test.tsx', 'jsdom']],
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    // hljs / pptx（含 echarts）/ antd 单 chunk 可能 >1100kB；阈值略高于默认以避免误导性告警
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (!id.includes('node_modules')) return
          // react + react-dom + scheduler 同桶，避免 vendor ↔ react-dom 循环 chunk
          if (
            id.includes('node_modules/react-dom') ||
            id.includes('node_modules/react/') ||
            id.includes('node_modules/scheduler')
          ) {
            return 'vendor-react-core'
          }
          if (id.includes('node_modules/react-router')) return 'vendor-router'
          if (id.includes('node_modules/react-i18next') || id.includes('node_modules/i18next')) {
            return 'vendor-i18n'
          }
          // Ant Design 全家桶单 chunk，避免 icons/cssinjs/rc 与 antd 之间循环依赖
          if (
            id.includes('node_modules/antd') ||
            id.includes('node_modules/rc-') ||
            id.includes('node_modules/@ant-design/icons') ||
            id.includes('node_modules/@ant-design/cssinjs') ||
            id.includes('node_modules/@rc-component')
          ) {
            return 'vendor-antd'
          }
          if (id.includes('node_modules/highlight.js')) return 'vendor-hljs'
          if (id.includes('node_modules/marked')) return 'vendor-marked'
          if (id.includes('node_modules/katex') || id.includes('node_modules/marked-katex-extension')) {
            return 'vendor-katex'
          }
          if (id.includes('node_modules/axios')) return 'vendor-axios'
          if (id.includes('node_modules/zustand')) return 'vendor-zustand'
          if (id.includes('node_modules/docx-preview')) return 'vendor-docx-preview'
          // echarts + zrender 单独分桶，避免与 pptx 主包合并后超过告警阈值
          if (id.includes('node_modules/echarts')) return 'vendor-echarts'
          if (id.includes('node_modules/zrender')) return 'vendor-echarts'
          if (id.includes('node_modules/pptx-preview')) return 'vendor-pptx-preview'
          if (id.includes('node_modules/lodash')) return 'vendor-pptx-preview'
          if (id.includes('node_modules/xlsx')) return 'vendor-xlsx'
          return 'vendor'
        },
      },
    },
  },
})
