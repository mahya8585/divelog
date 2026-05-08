import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import HomeView from './views/HomeView.vue'
import DetailView from './views/DetailView.vue'
import UploadView from './views/UploadView.vue'
import LoginView from './views/LoginView.vue'
import { useAuth } from './composables/useAuth.js'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: LoginView, meta: { public: true } },
    { path: '/', component: HomeView },
    { path: '/dive/:id', component: DetailView },
    { path: '/upload', component: UploadView },
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
app.mount('#app')
