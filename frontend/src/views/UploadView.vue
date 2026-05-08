<template>
  <div class="container py-4">
    <!-- 戻るボタン -->
    <router-link to="/" class="btn-back mb-3 d-inline-block">
      <i class="bi bi-chevron-left"></i> 一覧に戻る
    </router-link>

    <div class="section-card" style="max-width: 560px; margin: 0 auto;">
      <div class="section-title">
        <i class="bi bi-cloud-upload me-1"></i>ダイブログ登録
      </div>
      <p class="text-muted small mb-3">
        ダイブコンピュータから出力された <strong>.zxu</strong> ファイルを選択してください。<br>
        ファイルを変換して自動的に登録します。
      </p>

      <!-- ドロップゾーン -->
      <div
        class="drop-zone mb-3"
        :class="{ 'drop-zone--over': isDragOver }"
        @dragover.prevent="isDragOver = true"
        @dragleave.prevent="isDragOver = false"
        @drop.prevent="onDrop"
        @click="triggerFileInput"
      >
        <i class="bi bi-file-earmark-arrow-up fs-2 text-ocean mb-2"></i>
        <div v-if="selectedFile" class="fw-semibold text-ocean">{{ selectedFile.name }}</div>
        <div v-else class="text-muted small">
          クリックまたはドラッグ＆ドロップ<br>（.zxu ファイル）
        </div>
        <input
          ref="fileInputRef"
          type="file"
          accept=".zxu"
          class="d-none"
          @change="onFileChange"
        />
      </div>

      <!-- エラー -->
      <div v-if="errorMsg" class="alert alert-danger py-2 small">
        <i class="bi bi-exclamation-triangle me-1"></i>{{ errorMsg }}
      </div>

      <!-- 成功 -->
      <div v-if="successMsg" class="alert alert-success py-2 small">
        <i class="bi bi-check-circle me-1"></i>{{ successMsg }}
        <router-link v-if="registeredId" :to="`/dive/${registeredId}`" class="ms-2 fw-semibold">
          詳細を見る
        </router-link>
      </div>

      <!-- 送信ボタン -->
      <button
        class="btn btn-primary w-100"
        :disabled="!selectedFile || uploading"
        @click="doUpload"
      >
        <span v-if="uploading" class="spinner-border spinner-border-sm me-2" role="status"></span>
        <i v-else class="bi bi-cloud-upload me-1"></i>
        {{ uploading ? '登録中...' : '登録する' }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { uploadDive } from '../api/dives.js'

const fileInputRef  = ref(null)
const selectedFile = ref(null)
const uploading    = ref(false)
const errorMsg     = ref('')
const successMsg   = ref('')
const registeredId = ref('')
const isDragOver   = ref(false)

function triggerFileInput() {
  fileInputRef.value?.click()
}

function onFileChange(e) {
  const file = e.target.files?.[0]
  if (file) selectFile(file)
}

function onDrop(e) {
  isDragOver.value = false
  const file = e.dataTransfer.files?.[0]
  if (file) selectFile(file)
}

function selectFile(file) {
  errorMsg.value   = ''
  successMsg.value = ''
  registeredId.value = ''
  if (!file.name.toLowerCase().endsWith('.zxu')) {
    errorMsg.value = 'ZXU ファイルのみ対応しています。'
    selectedFile.value = null
    return
  }
  const MAX_SIZE = 5 * 1024 * 1024 // 5 MB
  if (file.size === 0 || file.size > MAX_SIZE) {
    errorMsg.value = 'ファイルサイズは 1 バイト～5 MB の範囲で選択してください。'
    selectedFile.value = null
    return
  }
  selectedFile.value = file
}

async function doUpload() {
  if (!selectedFile.value) return
  uploading.value  = true
  errorMsg.value   = ''
  successMsg.value = ''
  registeredId.value = ''
  try {
    const result = await uploadDive(selectedFile.value)
    registeredId.value = result.dive_id
    successMsg.value = `登録が完了しました（ID: ${result.dive_id}）`
    selectedFile.value = null
    if (fileInputRef.value) fileInputRef.value.value = ''
  } catch (e) {
    errorMsg.value = e.message || '登録に失敗しました。'
  } finally {
    uploading.value = false
  }
}
</script>

<style scoped>
.text-ocean { color: var(--ocean-teal); }

.drop-zone {
  border: 2px dashed var(--ocean-teal);
  border-radius: 12px;
  padding: 2rem 1rem;
  text-align: center;
  cursor: pointer;
  transition: background .15s, border-color .15s;
  display: flex;
  flex-direction: column;
  align-items: center;
}
.drop-zone:hover,
.drop-zone--over {
  background: rgba(0, 180, 216, .07);
  border-color: var(--ocean-mid);
}
</style>
