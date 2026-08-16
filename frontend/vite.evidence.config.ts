import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react-swc'
import { createReadStream, existsSync } from 'fs'
import { resolve } from 'path'

/** 116 视觉验收专用入口 — 仅本地 evidence 截图，不进入生产 bundle */
export default defineConfig({
  plugins: [
    react(),
    {
      name: 'mq-factory-evidence-public-assets',
      configureServer(server) {
        server.middlewares.use('/assets/mq-factory/illustrated/', (req, res, next) => {
          const filename = req.url?.replace(/^\//, '').replace(/\?.*$/, '')
          if (!filename || filename.includes('..')) {
            next()
            return
          }
          const filePath = resolve(__dirname, 'public/assets/mq-factory/illustrated', filename)
          if (!existsSync(filePath)) {
            next()
            return
          }
          res.setHeader('Content-Type', 'image/png')
          createReadStream(filePath).pipe(res)
        })
      },
    },
  ],
  root: resolve(__dirname, 'evidence/mq-factory'),
  publicDir: false,
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5199,
    strictPort: true,
  },
  preview: {
    port: 5199,
    strictPort: true,
  },
  build: {
    outDir: resolve(__dirname, 'dist-evidence-mq-factory'),
    emptyOutDir: true,
  },
})
