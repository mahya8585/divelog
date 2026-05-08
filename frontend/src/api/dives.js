/**
 * バックエンド API クライアント
 * VITE_API_BASE_URL 未設定時はプロキシ経由 (開発) or 同一オリジン (本番) を使用
 */
import { useAuth } from '../composables/useAuth.js'

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

/**
 * 認証ヘッダーを付与した fetch ラッパー
 */
function apiFetch(url, options = {}) {
  const { getToken } = useAuth()
  const token = getToken()
  const headers = {
    ...options.headers,
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
  return fetch(url, { ...options, headers })
}

/**
 * ダイブ一覧を取得する
 * @param {Object} params - { tag, year, month, location }
 * @returns {Promise<{dives, total, has_search, heatmap_data, markers_data}>}
 */
export async function fetchDives(params = {}) {
  const url = new URL(`${BASE_URL}/api/dives`, window.location.origin)
  Object.entries(params).forEach(([k, v]) => {
    if (v) url.searchParams.set(k, v)
  })
  const res = await apiFetch(url.toString())
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

/**
 * ZXU ファイルをアップロードしてダイブを登録する
 * @param {File} file - .zxu ファイル
 * @returns {Promise<{dive_id?: string, upload_id?: string, message: string}>}
 */
export async function uploadDive(file) {
  const formData = new FormData()
  formData.append('file', file)
  const res = await apiFetch(`${BASE_URL}/api/dives/upload`, {
    method: 'POST',
    body: formData,
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.error || `API error: ${res.status}`)
  return data
}

/**
 * ダイブ詳細を取得する
 * @param {string} diveId
 * @returns {Promise<{dive, tags}>}
 */
export async function fetchDive(diveId) {
  const res = await apiFetch(`${BASE_URL}/api/dives/${encodeURIComponent(diveId)}`)
  if (res.status === 404) throw new Error('NOT_FOUND')
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}
