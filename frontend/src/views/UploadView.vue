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
      <div v-if="successMsg" :class="['alert', 'py-2', 'small', wasOverwritten ? 'alert-warning' : 'alert-success']">
        <i :class="['bi', 'me-1', wasOverwritten ? 'bi-exclamation-triangle' : 'bi-check-circle']"></i>{{ successMsg }}
        <router-link v-if="registeredId" :to="`/dive/${registeredId}`" class="ms-2 fw-semibold">
          詳細を見る
        </router-link>
      </div>

      <div v-if="suggestion" class="alert alert-info py-2 small">
        <div class="fw-semibold mb-1">GPS 提案 (ロケーション名 「{{ suggestion.place_canonical || '不明' }}」)</div>
        <div>現在の GPS:
          <span v-if="suggestion.current_lat != null && suggestion.current_lon != null">
            {{ suggestion.current_lat.toFixed(5) }}, {{ suggestion.current_lon.toFixed(5) }}
          </span>
          <span v-else class="text-muted">未設定</span>
        </div>
        <div>提案 GPS: {{ suggestion.suggested_lat?.toFixed(5) }}, {{ suggestion.suggested_lon?.toFixed(5) }}</div>
        <div class="text-muted">
          信頼度: {{ (suggestion.confidence ?? 0).toFixed(2) }} /
          ソース: {{ suggestion.source }}
          <span v-if="suggestion.distance_km != null">/ 距離: {{ suggestion.distance_km.toFixed(1) }} km</span>
        </div>
        <div class="mt-2 d-flex gap-2">
          <button class="btn btn-sm btn-success" :disabled="uploading" @click="decide(true)">承認して登録</button>
          <button class="btn btn-sm btn-outline-secondary" :disabled="uploading" @click="decide(false)">そのまま登録</button>
        </div>
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
import { confirmUpload, uploadDive } from '../api/dives.js'

const fileInputRef  = ref(null)
const selectedFile = ref(null)
const uploading    = ref(false)
const errorMsg     = ref('')
const successMsg   = ref('')
const registeredId = ref('')
const wasOverwritten = ref(false)
const isDragOver   = ref(false)
const pendingUploadId = ref('')
const suggestion = ref(null)

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
  pendingUploadId.value = ''
  suggestion.value = null
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
  wasOverwritten.value = false
  suggestion.value = null
  const fileToSend = selectedFile.value
  try {
    const result = await uploadDive(fileToSend)
    handleUploadResult(result, fileToSend)
  } catch (e) {
    errorMsg.value = e.message || '登録に失敗しました。'
  } finally {
    uploading.value = false
  }
}

function handleUploadResult(result, fileToSend) {
  if (result.dive_id) {
    registeredId.value = result.dive_id
    wasOverwritten.value = !!result.overwritten
    successMsg.value = result.overwritten
      ? `既存のダイブログを上書きしました（ID: ${result.dive_id}）`
      : `登録が完了しました（ID: ${result.dive_id}）`
    selectedFile.value = null
    if (fileInputRef.value) fileInputRef.value.value = ''
    return
  }
  if (result.gps_suggestion) {
    suggestion.value = result.gps_suggestion
    pendingUploadId.value = result.upload_id || ''
    // Cosmos 無効モードではファイルを保持して再送信に備える
    if (!pendingUploadId.value) {
      pendingFile.value = fileToSend
    } else {
      selectedFile.value = null
      if (fileInputRef.value) fileInputRef.value.value = ''
    }
    successMsg.value = 'GPS 提案があります。承認または却下を選択してください。'
    return
  }
  successMsg.value = result.message || 'アップロードを受け付けました。'
  selectedFile.value = null
  if (fileInputRef.value) fileInputRef.value.value = ''
}

const pendingFile = ref(null)

async function decide(accept) {
  if (!suggestion.value) return
  uploading.value = true
  errorMsg.value = ''
  try {
    if (pendingUploadId.value) {
      // Cosmos モード: confirm エンドポイントを呼ぶ
      const result = await confirmUpload(pendingUploadId.value, {
        accept,
        suggestedLat: accept ? suggestion.value.suggested_lat : undefined,
        suggestedLon: accept ? suggestion.value.suggested_lon : undefined,
      })
      suggestion.value = null
      pendingUploadId.value = ''
      successMsg.value = accept
        ? '提案を承認しました。バックグラウンドでダイブを登録します。'
        : '提案を却下しました。元の情報でダイブを登録します。'
      if (result?.status) successMsg.value += `（ステータス: ${result.status}）`
    } else if (pendingFile.value) {
      // Cosmos 無効モード: 同じファイルを再送信
      const opts = accept
        ? {
            applySuggestion: true,
            gpsOverrideLat: suggestion.value.suggested_lat,
            gpsOverrideLon: suggestion.value.suggested_lon,
          }
        : {}
      const result = await uploadDive(pendingFile.value, opts)
      suggestion.value = null
      pendingFile.value = null
      handleUploadResult(result, null)
    }
  } catch (e) {
    errorMsg.value = e.message || '提案処理に失敗しました。'
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
