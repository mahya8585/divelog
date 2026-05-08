<template>
  <!-- ヒートマップ -->
  <div id="heatmap" class="map-container w-100"></div>

  <div class="container py-4">
    <!-- 検索フォーム -->
    <div class="search-card card mb-4">
      <div class="card-body">
        <div class="row g-2 align-items-end">
          <div class="col-md-3">
            <label class="form-label small mb-1">
              <i class="bi bi-tag me-1"></i>タグ（部分一致）
            </label>
            <input v-model="form.tag" type="text" class="form-control form-control-sm"
                   placeholder="例: ウミウシ" @keyup.enter="doSearch" />
          </div>
          <div class="col-md-2">
            <label class="form-label small mb-1">
              <i class="bi bi-calendar me-1"></i>年
            </label>
            <input v-model="form.year" type="text" class="form-control form-control-sm"
                   placeholder="例: 2025" maxlength="4" @keyup.enter="doSearch" />
          </div>
          <div class="col-md-2">
            <label class="form-label small mb-1">月</label>
            <input v-model="form.month" type="text" class="form-control form-control-sm"
                   placeholder="12" maxlength="2" @keyup.enter="doSearch" />
          </div>
          <div class="col-md-3">
            <label class="form-label small mb-1">
              <i class="bi bi-geo-alt me-1"></i>ロケーション（部分一致）
            </label>
            <input v-model="form.location" type="text" class="form-control form-control-sm"
                   placeholder="例: 沖縄本島" @keyup.enter="doSearch" />
          </div>
          <div class="col-md-2 d-flex gap-2">
            <button class="btn btn-primary btn-sm w-100" @click="doSearch">
              <i class="bi bi-search me-1"></i>検索
            </button>
            <button v-if="hasSearch" class="btn btn-outline-secondary btn-sm" @click="clearSearch" title="クリア">
              <i class="bi bi-x-lg"></i>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 件数表示 -->
    <div class="d-flex align-items-center gap-2 mb-3">
      <h6 class="mb-0"><i class="bi bi-list-ul me-1"></i>ダイブログ</h6>
      <span class="badge bg-secondary">{{ dives.length }} 件</span>
      <span v-if="hasSearch" class="text-muted small">検索中</span>
    </div>

    <!-- ローディング -->
    <div v-if="loading" class="text-center py-5">
      <div class="spinner-border text-primary" role="status"><span class="visually-hidden">読み込み中</span></div>
      <div class="mt-2 text-muted small">
        <i class="bi bi-arrow-repeat me-1"></i>データ取得中
      </div>
    </div>

    <!-- エラー -->
    <div v-else-if="error" class="alert alert-danger">{{ error }}</div>

    <!-- ダイブリスト -->
    <template v-else>
      <router-link
        v-for="dive in dives"
        :key="dive.dive_id"
        :to="`/dive/${dive.dive_id}`"
        class="dive-card"
      >
        <div class="d-flex align-items-center gap-3">
          <div class="dive-number-circle">#{{ dive.dive_info.dive_number }}</div>
          <div class="flex-grow-1 min-width-0">
            <div class="fw-semibold text-truncate">{{ formatDate(dive.dive_info.datetime) }}</div>
            <div class="text-muted small">
              <i class="bi bi-geo-alt-fill me-1"></i>
              {{ dive.location?.name || '—' }}
            </div>
          </div>
          <div class="text-warning">{{ stars(dive.dive_info.rating) }}</div>
        </div>
      </router-link>

      <div v-if="dives.length === 0" class="text-center text-muted py-4">
        該当するダイブログがありません
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { fetchDives } from '../api/dives.js'

const route  = useRoute()
const router = useRouter()

const dives    = ref([])
const loading  = ref(true)
const error    = ref(null)
const heatmapData  = ref([])
const markersData  = ref([])

const form = reactive({
  tag:      route.query.tag      || '',
  year:     route.query.year     || '',
  month:    route.query.month    || '',
  location: route.query.location || '',
})

const hasSearch = computed(() =>
  !!(form.tag || form.year || form.month || form.location)
)

// ── ユーティリティ ─────────────────────────────────────
const WEEKDAYS = ['月', '火', '水', '木', '金', '土', '日']
function formatDate(dtStr) {
  if (!dtStr) return ''
  const dt  = new Date(dtStr)
  const dow = WEEKDAYS[dt.getDay() === 0 ? 6 : dt.getDay() - 1]
  return `${dt.getFullYear()}年${dt.getMonth() + 1}月${dt.getDate()}日（${dow}）`
}
function stars(rating) {
  const r = Math.max(0, Math.min(5, Number(rating) || 0))
  return '★'.repeat(r) + '☆'.repeat(5 - r)
}

// ── Leaflet ヒートマップ ───────────────────────────────
let leafletMap = null
let heatLayer  = null
let markerLayer = null

function initMap() {
  const L = window.L
  if (!L || leafletMap) return
  leafletMap = L.map('heatmap', { zoomControl: true }).setView([26.5, 127.9], 10)
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(leafletMap)
}

function updateMap() {
  const L = window.L
  if (!L || !leafletMap) return

  // ヒートレイヤー
  if (heatLayer) leafletMap.removeLayer(heatLayer)
  if (heatmapData.value.length) {
    heatLayer = L.heatLayer(heatmapData.value, {
      radius: 35, blur: 20, maxZoom: 13,
      gradient: { 0.3: '#48cae4', 0.6: '#0096c7', 1.0: '#0a1628' },
    }).addTo(leafletMap)
  }

  // マーカー
  if (markerLayer) leafletMap.removeLayer(markerLayer)
  markerLayer = L.layerGroup()
  markersData.value.forEach(m => {
    L.circleMarker([m.lat, m.lon], {
      radius: 10 + m.count * 2,
      fillColor: '#00b4d8', color: '#fff',
      weight: 2, opacity: 1, fillOpacity: 0.7,
    })
      .bindPopup(`<strong>${m.name}</strong><br>${m.count} ダイブ`)
      .addTo(markerLayer)
  })
  markerLayer.addTo(leafletMap)
}

// ── データ取得 ────────────────────────────────────────
async function loadDives() {
  loading.value = true
  error.value   = null
  try {
    const data = await fetchDives({
      tag:      form.tag,
      year:     form.year,
      month:    form.month,
      location: form.location,
    })
    dives.value       = data.dives
    heatmapData.value = data.heatmap_data
    markersData.value = data.markers_data
    updateMap()
  } catch (e) {
    error.value = 'データの取得に失敗しました。バックエンドが起動しているか確認してください。'
  } finally {
    loading.value = false
  }
}

function doSearch() {
  router.replace({ query: {
    ...(form.tag      ? { tag:      form.tag }      : {}),
    ...(form.year     ? { year:     form.year }     : {}),
    ...(form.month    ? { month:    form.month }    : {}),
    ...(form.location ? { location: form.location } : {}),
  }})
  loadDives()
}

function clearSearch() {
  form.tag = form.year = form.month = form.location = ''
  router.replace({ query: {} })
  loadDives()
}

// クエリパラメータ変化に追従（ブラウザバック等）
watch(() => route.query, q => {
  form.tag      = q.tag      || ''
  form.year     = q.year     || ''
  form.month    = q.month    || ''
  form.location = q.location || ''
})

onMounted(async () => {
  initMap()
  await loadDives()
})
</script>
