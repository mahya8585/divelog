import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import HomeView from './views/HomeView.vue'
import DetailView from './views/DetailView.vue'
import UploadView from './views/UploadView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: HomeView },
    { path: '/dive/:id', component: DetailView },
    { path: '/upload', component: UploadView },
  ],
})

const app = createApp(App)
app.use(router)
app.mount('#app')
