/**
 * バックエンド API クライアント
 * VITE_API_BASE_URL 未設定時はプロキシ経由 (開発) or 同一オリジン (本番) を使用
 */
const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

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
  const res = await fetch(url.toString())
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

/**
 * ダイブ詳細を取得する
 * @param {string} diveId
 * @returns {Promise<{dive, tags}>}
 */
export async function fetchDive(diveId) {
  const res = await fetch(`${BASE_URL}/api/dives/${encodeURIComponent(diveId)}`)
  if (res.status === 404) throw new Error('NOT_FOUND')
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}
