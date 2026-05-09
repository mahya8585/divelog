/**
 * staticwebapp.config.json の CSP `connect-src` 内にあるプレースホルダ
 * `__BACKEND_ORIGIN__` を、ビルド時の VITE_API_BASE_URL の origin に置換し、
 * `dist/staticwebapp.config.json` として出力する。
 *
 * - VITE_API_BASE_URL 未設定 / 不正 URL: プレースホルダを除去（'self' のみ許可）。
 * - これにより `*.azurecontainerapps.io` のようなワイルドカード許可をやめ、
 *   実際のバックエンド FQDN だけを CSP で許可する。
 */
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const root = resolve(__dirname, '..')
const src  = resolve(root, 'staticwebapp.config.json')
const dst  = resolve(root, 'dist', 'staticwebapp.config.json')

let backendOrigin = ''
const raw = process.env.VITE_API_BASE_URL || ''
if (raw) {
  try {
    backendOrigin = new URL(raw).origin
  } catch {
    console.warn(`[process-swa-config] VITE_API_BASE_URL が不正な URL です: ${raw}`)
  }
}

const text = readFileSync(src, 'utf8')
const replaced = text.replaceAll('__BACKEND_ORIGIN__', backendOrigin).replace(/\s{2,}/g, ' ')

mkdirSync(dirname(dst), { recursive: true })
writeFileSync(dst, replaced, 'utf8')
console.log(`[process-swa-config] wrote ${dst} (backend origin: ${backendOrigin || '(none, self only)'})`)
