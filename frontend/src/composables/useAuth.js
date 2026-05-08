/**
 * 認証状態管理コンポーザブル
 * - sessionStorage にトークンを保存
 * - 10 分間操作がなければ自動ログアウト
 */
import { ref, computed } from 'vue'

const STORAGE_KEY = 'divelog_token'
const INACTIVITY_TIMEOUT_MS = 10 * 60 * 1000 // 10 分

// モジュールレベルのシングルトン状態
const _token = ref(sessionStorage.getItem(STORAGE_KEY) || '')
const isAuthenticated = computed(() => !!_token.value)

let _router = null
let _inactivityTimer = null

// マウス移動は頻度が高いため除外し、mousedown/click/keydown/scroll/touchstart のみ追跡する
const ACTIVITY_EVENTS = ['mousedown', 'keydown', 'scroll', 'touchstart']

function _resetTimer() {
  clearTimeout(_inactivityTimer)
  if (_token.value) {
    _inactivityTimer = setTimeout(_doLogout, INACTIVITY_TIMEOUT_MS)
  }
}

async function _doLogout() {
  const token = _token.value
  _token.value = ''
  sessionStorage.removeItem(STORAGE_KEY)
  ACTIVITY_EVENTS.forEach(ev => window.removeEventListener(ev, _resetTimer))
  clearTimeout(_inactivityTimer)
  // サーバー側のトークンを削除（失敗しても続行）
  if (token) {
    fetch('/api/logout', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    }).catch((err) => {
      if (import.meta.env.DEV) {
        console.warn('[useAuth] logout request failed:', err)
      }
    })
  }
  if (_router) {
    _router.push('/login')
  }
}

function _startTracking() {
  ACTIVITY_EVENTS.forEach(ev =>
    window.addEventListener(ev, _resetTimer, { passive: true })
  )
  _resetTimer()
}

/**
 * ログイン処理: バックエンドに認証リクエストを送り、トークンを保存する。
 * @param {string} email
 * @param {string} password
 */
async function login(email, password) {
  const res = await fetch('/api/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    throw new Error(data.error || 'ログインに失敗しました')
  }
  _token.value = data.token
  sessionStorage.setItem(STORAGE_KEY, data.token)
  _startTracking()
}

/**
 * ログアウト処理: トークンを削除し、ログイン画面にリダイレクトする。
 */
function logout() {
  _doLogout()
}

/**
 * Vue Router インスタンスを登録する（main.js から呼び出す）。
 * @param {import('vue-router').Router} router
 */
function setRouter(router) {
  _router = router
}

/**
 * 現在のトークン値を返す（API リクエスト用）。
 * @returns {string}
 */
function getToken() {
  return _token.value
}

// ページリロード後もトークンがあればタイマーを再開
if (_token.value) {
  _startTracking()
}

export function useAuth() {
  return {
    isAuthenticated,
    login,
    logout,
    setRouter,
    getToken,
  }
}
