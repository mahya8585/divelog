/**
 * 文字列内の HTML 特殊文字をエスケープするユーティリティ関数。
 * v-html や Leaflet の bindPopup など、生 HTML を扱う箇所でプレーンテキストを安全に埋め込む用途に使用する。
 *
 * 注意: 既にHTMLエンティティを含む文字列（例: "&amp;lt;"）を渡すと二重エスケープされる。
 * この関数はデータベースや外部入力から取得したプレーンテキストのみを対象とすること。
 *
 * @param {string|null|undefined} str - エスケープする文字列。null/undefined/空値は空文字列として扱う。
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
