/**
 * ロケーション API クライアント
 */
import { useAuth } from '../composables/useAuth.js'

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

function apiFetch(url, options = {}) {
  const { getToken, logout } = useAuth()
  const token = getToken()
  const headers = {
    ...options.headers,
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
  return fetch(url, { ...options, headers }).then((res) => {
    if (res.status === 401) {
      logout()
    }
    return res
  })
}

/**
 * ユニークなロケーション一覧を取得する
 * @returns {Promise<{locations: Array}>}
 */
export async function fetchLocations() {
  const res = await apiFetch(`${BASE_URL}/api/locations`)
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

/**
 * ロケーション知識の GPS を更新する（同名ダイブの GPS も一括更新）
 * @param {string} normName - 正規化ロケーション名
 * @param {{ canonical_name: string, gps_lat: number, gps_lon: number }} data
 * @returns {Promise<{ updated: boolean, dives_updated: number }>}
 */
export async function updateLocationKnowledge(normName, data) {
  const res = await apiFetch(
    `${BASE_URL}/api/locations/knowledge/${encodeURIComponent(normName)}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    },
  )
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(body.error || `API error: ${res.status}`)
  return body
}
