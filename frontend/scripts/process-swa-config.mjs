/**
 * staticwebapp.config.json の CSP 内プレースホルダをビルド時に置換し、
 * `dist/staticwebapp.config.json` として出力する。
 *
 * - __APPINSIGHTS_INGESTION_ORIGIN__ : VITE_APPINSIGHTS_CONNECTION_STRING から
 *                                  IngestionEndpoint を抽出した origin（ワイルドカード不要）
 *
 * バックエンド URL は埋め込まない。SPA は相対パス `/api/*` で動作し、SWA Linked Backend
 * が Container Apps へエッジ転送するため、ブラウザから見れば同一オリジン。
 * 未設定 / 不正な値は空文字列に置換され、CSP は 'self' のみ許可される。
 */
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const root = resolve(__dirname, '..')
const src  = resolve(root, 'staticwebapp.config.json')
const dst  = resolve(root, 'dist', 'staticwebapp.config.json')

function toOrigin(rawUrl) {
  if (!rawUrl) return ''
  try {
    return new URL(rawUrl).origin
  } catch {
    console.warn(`[process-swa-config] invalid URL: ${rawUrl}`)
    return ''
  }
}

// Application Insights 接続文字列から IngestionEndpoint を抽出
let aiIngestionOrigin = ''
const aiConn = process.env.VITE_APPINSIGHTS_CONNECTION_STRING || ''
if (aiConn) {
  const m = /IngestionEndpoint=([^;]+)/i.exec(aiConn)
  if (m) aiIngestionOrigin = toOrigin(m[1].trim())
}

const text = readFileSync(src, 'utf8')
const replaced = text
  .replaceAll('__APPINSIGHTS_INGESTION_ORIGIN__', aiIngestionOrigin)
  .replace(/\s{2,}/g, ' ')

mkdirSync(dirname(dst), { recursive: true })
writeFileSync(dst, replaced, 'utf8')
console.log(`[process-swa-config] wrote ${dst}`)
console.log(`  appinsights origin: ${aiIngestionOrigin || '(self only)'}`)
