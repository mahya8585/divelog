<template>
  <div class="login-wrapper d-flex align-items-center justify-content-center min-vh-100">
    <div class="login-card">
      <div class="text-center mb-4">
        <i class="bi bi-water fs-1 text-ocean"></i>
        <h4 class="fw-bold mt-2 mb-0">Dive Log</h4>
        <p class="text-muted small mt-1">ログインしてください</p>
      </div>

      <form @submit.prevent="doLogin">
        <div class="mb-3">
          <label for="email" class="form-label small fw-semibold">
            <i class="bi bi-envelope me-1"></i>メールアドレス
          </label>
          <input
            id="email"
            v-model="email"
            type="email"
            class="form-control"
            placeholder="your@email.com"
            autocomplete="email"
            required
          />
        </div>

        <div class="mb-4">
          <label for="password" class="form-label small fw-semibold">
            <i class="bi bi-lock me-1"></i>パスワード
          </label>
          <input
            id="password"
            v-model="password"
            type="password"
            class="form-control"
            placeholder="パスワード"
            autocomplete="current-password"
            required
          />
        </div>

        <div v-if="errorMsg" class="alert alert-danger py-2 small mb-3">
          <i class="bi bi-exclamation-triangle me-1"></i>{{ errorMsg }}
        </div>

        <button
          type="submit"
          class="btn btn-primary w-100"
          :disabled="loading"
        >
          <span v-if="loading" class="spinner-border spinner-border-sm me-2" role="status"></span>
          <i v-else class="bi bi-box-arrow-in-right me-1"></i>
          {{ loading ? 'ログイン中...' : 'ログイン' }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuth } from '../composables/useAuth.js'

const router = useRouter()
const route  = useRoute()
const { login } = useAuth()

const email    = ref('')
const password = ref('')
const loading  = ref(false)
const errorMsg = ref('')

async function doLogin() {
  loading.value  = true
  errorMsg.value = ''
  try {
    await login(email.value, password.value)
    const redirect = route.query.redirect
    router.push(typeof redirect === 'string' && redirect.startsWith('/') ? redirect : '/')
  } catch (e) {
    errorMsg.value = e.message || 'ログインに失敗しました'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-wrapper {
  background: linear-gradient(135deg, var(--ocean-dark), var(--ocean-mid));
  min-height: 100vh;
}

.login-card {
  background: #fff;
  border-radius: 16px;
  padding: 2rem 2.25rem;
  width: 100%;
  max-width: 400px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, .25);
}

.text-ocean { color: var(--ocean-teal); }
</style>
