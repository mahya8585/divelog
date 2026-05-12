import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'

// スタイル / 3rd party ライブラリをバンドルに取り込む（サプライチェーン対策、CSP 'self' のみ）
import 'bootstrap/dist/css/bootstrap.min.css'
import 'bootstrap-icons/font/bootstrap-icons.css'
import 'leaflet/dist/leaflet.css'
import L from 'leaflet'
import 'leaflet.heat'
// 既存コードが window.L を使うためグローバルに公開
window.L = L

import App from './App.vue'
import HomeView from './views/HomeView.vue'
import DetailView from './views/DetailView.vue'
import UploadView from './views/UploadView.vue'
import LoginView from './views/LoginView.vue'
import LocationsView from './views/LocationsView.vue'
import { useAuth } from './composables/useAuth.js'
import { trackError } from './appInsights.js'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: LoginView, meta: { public: true } },
    { path: '/', component: HomeView },
    { path: '/dive/:id', component: DetailView },
    { path: '/upload', component: UploadView },
    { path: '/locations', component: LocationsView },
  ],
})

// ナビゲーションガード: 未認証の場合はログイン画面にリダイレクト
router.beforeEach((to) => {
  const { isAuthenticated } = useAuth()
  if (!to.meta.public && !isAuthenticated.value) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
})

const { setRouter } = useAuth()
setRouter(router)

const app = createApp(App)
app.use(router)

// Vue の未処理エラーを Application Insights へ転送（ERROR レベル）
app.config.errorHandler = (err, _instance, info) => {
  trackError(err, { vueInfo: info })
}

// ブラウザの未処理例外・Promise 拒否を Application Insights へ転送（ERROR レベル）
window.addEventListener('error', (event) => {
  trackError(event.error ?? new Error(event.message), {
    source: event.filename ?? '',
    line: String(event.lineno ?? ''),
  })
})
window.addEventListener('unhandledrejection', (event) => {
  const reason = event.reason
  trackError(reason instanceof Error ? reason : new Error(String(reason)), {
    type: 'unhandledrejection',
  })
})

app.mount('#app')
