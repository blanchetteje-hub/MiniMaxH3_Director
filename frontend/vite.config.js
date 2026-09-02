import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

// Chromium blocks file:// pages from importing neighboring module files. Keep
// Vite for development, but inline the production JS and CSS so pywebview can
// load dist/index.html directly without quietly starting an HTTP server.
function inlineLocalFileAssets() {
  return {
    name: 'inline-local-file-assets',
    apply: 'build',
    enforce: 'post',
    closeBundle() {
      const distDirectory = fileURLToPath(new URL('./dist/', import.meta.url))
      const indexPath = resolve(distDirectory, 'index.html')
      let html = readFileSync(indexPath, 'utf8')

      html = html.replace(
        /<link rel="stylesheet"[^>]*href="([^"]+)"[^>]*>/g,
        (_tag, href) => {
          const css = readFileSync(resolve(distDirectory, href), 'utf8')
          return `<style>${css.replaceAll('</style', '<\\/style')}</style>`
        },
      )
      html = html.replace(
        /<script type="module"[^>]*src="([^"]+)"[^>]*><\/script>/g,
        (_tag, source) => {
          const javascript = readFileSync(resolve(distDirectory, source), 'utf8')
          return `<script type="module">${javascript.replaceAll('</script', '<\\/script')}</script>`
        },
      )
      writeFileSync(indexPath, html, 'utf8')
    },
  }
}

export default defineConfig({
  plugins: [react(), inlineLocalFileAssets()],
  base: './',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
