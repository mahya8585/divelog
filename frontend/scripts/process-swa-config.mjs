/**
 * staticwebapp.config.json の CSP 内プレースホルダをビルド時に置換し、
 * `dist/staticwebapp.config.json` として出力する。
 *
 * - __BACKEND_ORIGIN__         : VITE_API_BASE_URL の origin
 * - __APPINSIGHTS_INGESTION_ORIGIN__ : VITE_APPINSIGHTS_CONNECTION_STRING から
 *                                  IngestionEndpoint を抽出した origin（ワイルドカード不要）
 * 環境変数は process.env → .env.production → .env の順に解決する。
 * 未設定 / 不正な値は空文字列に置換され、'self' のみ許可される。
 */
import { existsSync, readFileSync, writeFileSync, mkdirSync } from 'node:fs'
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

function loadDotenvFallback(name) {
  if (process.env[name]) return process.env[name]

  for (const file of ['.env.production', '.env']) {
    const path = resolve(root, file)
    if (!existsSync(path)) continue

    const line = readFileSync(path, 'utf8')
      .split(/\r?\n/)
      .find((entry) => entry.trim().startsWith(`${name}=`))
    if (!line) continue

    const value = line.trim().replace(new RegExp(`^${name}=`), '').trim().replace(/^(['"])(.*)\1$/, '$2')
    if (value) return value
  }

  return ''
}

let backendOrigin = toOrigin(loadDotenvFallback('VITE_API_BASE_URL'))

// Application Insights 接続文字列から IngestionEndpoint を抽出
let aiIngestionOrigin = ''
const aiConn = process.env.VITE_APPINSIGHTS_CONNECTION_STRING || ''
if (aiConn) {
  const m = /IngestionEndpoint=([^;]+)/i.exec(aiConn)
  if (m) aiIngestionOrigin = toOrigin(m[1].trim())
}

const text = readFileSync(src, 'utf8')
const replaced = text
  .replaceAll('__BACKEND_ORIGIN__', backendOrigin)
  .replaceAll('__APPINSIGHTS_INGESTION_ORIGIN__', aiIngestionOrigin)
  .replace(/\s{2,}/g, ' ')

mkdirSync(dirname(dst), { recursive: true })
writeFileSync(dst, replaced, 'utf8')
console.log(`[process-swa-config] wrote ${dst}`)
console.log(`  backend origin   : ${backendOrigin || '(self only)'}`)
console.log(`  appinsights origin: ${aiIngestionOrigin || '(self only)'}`)
