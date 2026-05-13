/**
 * バックエンド API クライアント
 *
 * URL は常に相対パス `/api/*` を使う：
 *   - 本番: SWA Linked Backend が /api/* を Container Apps にエッジ転送するため同一オリジンとなり、
 *           backend FQDN 変更や CORS を意識しなくてよい。
 *   - 開発: vite.config.js の proxy 設定で /api → http://localhost:8000 に転送される。
 */
import { useAuth } from '../composables/useAuth.js'

/**
 * 認証ヘッダーを付与した fetch ラッパー。
 * 401 が返った場合は期限切れ / 失効トークンとみなしてログアウト処理 (token クリア + /login 遷移) を行う。
 */
function apiFetch(url, options = {}) {
  const { getToken, logout } = useAuth()
  const token = getToken()
  const headers = {
    ...options.headers,
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
  return fetch(url, { ...options, headers }).then((res) => {
    if (res.status === 401) {
      // 期限切れトークン等。sessionStorage から token を削除しログイン画面へ。
      // logout() は非同期に /api/logout を呼び /login へ router.push する。
      logout()
    }
    return res
  })
}

/**
 * ダイブ一覧を取得する
 * @param {Object} params - { tag, year, month, location }
 * @returns {Promise<{dives, total, has_search, heatmap_data, markers_data}>}
 */
export async function fetchDives(params = {}) {
  const url = new URL(`/api/dives`, window.location.origin)
  Object.entries(params).forEach(([k, v]) => {
    if (v) url.searchParams.set(k, v)
  })
  const res = await apiFetch(url.toString())
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

/**
 * ZXU ファイルをアップロードしてダイブを登録する。
 * GPS 提案がある場合は gps_suggestion / status:'pending_review' が返る。
 * Cosmos 無効モードで提案を適用したい場合は apply_suggestion / gps_override_lat / gps_override_lon を指定して再送信する。
 * @param {File} file - .zxu ファイル
 * @param {Object} [opts]
 * @param {boolean} [opts.applySuggestion]
 * @param {number} [opts.gpsOverrideLat]
 * @param {number} [opts.gpsOverrideLon]
 * @returns {Promise<{dive_id?: string, upload_id?: string, status?: string, gps_suggestion?: object, message: string}>}
 */
export async function uploadDive(file, opts = {}) {
  const formData = new FormData()
  formData.append('file', file)
  const url = new URL(`/api/dives/upload`, window.location.origin)
  if (opts.applySuggestion) url.searchParams.set('apply_suggestion', 'true')
  if (opts.gpsOverrideLat != null) url.searchParams.set('gps_override_lat', String(opts.gpsOverrideLat))
  if (opts.gpsOverrideLon != null) url.searchParams.set('gps_override_lon', String(opts.gpsOverrideLon))
  const res = await apiFetch(url.toString().replace(window.location.origin, ''), {
    method: 'POST',
    body: formData,
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.error || `API error: ${res.status}`)
  return data
}

export async function fetchUploadStatus(uploadId) {
  const res = await apiFetch(`/api/dives/uploads/${encodeURIComponent(uploadId)}`)
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.error || `API error: ${res.status}`)
  return data
}

/**
 * GPS 提案の承認 / 却下をサーバーに送る。
 * @param {string} uploadId
 * @param {Object} payload
 * @param {boolean} payload.accept - trueで提案を適用、falseで却下しそのまま登録。
 * @param {number} [payload.suggestedLat]
 * @param {number} [payload.suggestedLon]
 */
export async function confirmUpload(uploadId, { accept, suggestedLat, suggestedLon }) {
  const body = { accept: !!accept }
  if (suggestedLat != null) body.suggested_lat = suggestedLat
  if (suggestedLon != null) body.suggested_lon = suggestedLon
  const res = await apiFetch(`/api/dives/uploads/${encodeURIComponent(uploadId)}/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
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
  const res = await apiFetch(`/api/dives/${encodeURIComponent(diveId)}`)
  if (res.status === 404) throw new Error('NOT_FOUND')
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}
