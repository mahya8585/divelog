/**
 * HTML 文字列をエスケープするユーティリティ関数。
 * v-html や Leaflet の bindPopup など、生 HTML を扱う箇所で使用する。
 * @param {string} str
 * @returns {string}
 */
export function escapeHtml(str) {
  return (str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#x27;')
}
