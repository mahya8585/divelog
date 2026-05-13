<template>
  <!-- ロケーションマップ -->
  <div id="locations-map" class="map-container w-100"></div>

  <div class="container py-4">
    <div class="d-flex align-items-center gap-2 mb-3">
      <h5 class="mb-0"><i class="bi bi-geo-alt-fill me-1"></i>ロケーション一覧</h5>
      <span class="badge bg-secondary">{{ locations.length }} 件</span>
    </div>

    <div v-if="loading" class="text-center py-5">
      <LoadingIndicator />
    </div>
    <div v-else-if="error" class="alert alert-danger">{{ error }}</div>

    <template v-else>
      <div class="section-card p-0 overflow-hidden">
        <div
          v-for="loc in locations"
          :key="loc.normalized_name"
          class="location-row"
          @click="openEdit(loc)"
        >
          <div class="d-flex align-items-center gap-3">
            <div class="location-icon">
              <i class="bi bi-geo-alt-fill"></i>
            </div>
            <div class="flex-grow-1 min-width-0">
              <div class="fw-semibold text-truncate">{{ loc.name }}</div>
              <div class="text-muted small">
                <span v-if="displayLat(loc) != null && displayLon(loc) != null">
                  GPS: {{ displayLat(loc).toFixed(5) }}, {{ displayLon(loc).toFixed(5) }}
                </span>
                <span v-else class="text-warning"><i class="bi bi-exclamation-triangle me-1"></i>GPS 未設定</span>
              </div>
            </div>
            <div class="text-end flex-shrink-0">
              <span class="badge bg-primary">{{ loc.dive_count }} ダイブ</span>
              <span v-if="loc.has_knowledge" class="badge bg-success ms-1" title="GPS ナレッジ登録済">
                <i class="bi bi-check-circle-fill"></i>
              </span>
            </div>
          </div>
        </div>
        <div v-if="locations.length === 0" class="text-center text-muted py-4">
          ロケーションデータがありません
        </div>
      </div>
    </template>
  </div>

  <!-- GPS 編集モーダル -->
  <Transition name="fade">
    <div v-if="editTarget" class="modal-overlay" @click.self="closeEdit">
      <div class="edit-panel">
        <div class="d-flex align-items-center mb-3">
          <h6 class="mb-0 flex-grow-1">
            <i class="bi bi-pencil-square me-1"></i>GPS 編集
          </h6>
          <button class="btn btn-link p-0 text-secondary" @click="closeEdit" aria-label="閉じる">
            <i class="bi bi-x-lg"></i>
          </button>
        </div>

        <div class="mb-3">
          <label class="form-label small mb-1">ロケーション名</label>
          <input
            v-model="editForm.canonical_name"
            type="text"
            class="form-control form-control-sm"
          />
        </div>
        <div class="row g-2 mb-3">
          <div class="col-6">
            <label class="form-label small mb-1">緯度 (Latitude)</label>
            <input
              v-model.number="editForm.gps_lat"
              @change="syncEditMapFromForm"
              type="number"
              step="any"
              min="-90"
              max="90"
              class="form-control form-control-sm"
              placeholder="例: 26.3944"
            />
          </div>
          <div class="col-6">
            <label class="form-label small mb-1">経度 (Longitude)</label>
            <input
              v-model.number="editForm.gps_lon"
              @change="syncEditMapFromForm"
              type="number"
              step="any"
              min="-180"
              max="180"
              class="form-control form-control-sm"
              placeholder="例: 127.8567"
            />
          </div>
        </div>
        <div class="mb-3">
          <label class="form-label small mb-1">地図で GPS を選択</label>
          <div id="edit-location-map" class="edit-map-container"></div>
          <div class="form-text">地図をクリック、またはマーカーをドラッグして位置を更新できます。</div>
        </div>

        <div v-if="editError" class="alert alert-danger py-2 small mb-2">{{ editError }}</div>
        <div v-if="editSuccess" class="alert alert-success py-2 small mb-2">{{ editSuccess }}</div>

        <div class="d-flex gap-2 justify-content-end">
          <button class="btn btn-outline-secondary btn-sm" @click="closeEdit">キャンセル</button>
          <button class="btn btn-primary btn-sm" @click="saveEdit" :disabled="saving">
            <span v-if="saving" class="spinner-border spinner-border-sm me-1" role="status"></span>
            保存
          </button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { fetchLocations, updateLocationKnowledge } from '../api/locations.js'
import LoadingIndicator from '../components/LoadingIndicator.vue'

const locations = ref([])
const loading   = ref(true)
const error     = ref(null)

// 編集モーダル
const editTarget  = ref(null)
const editForm    = ref({ canonical_name: '', gps_lat: null, gps_lon: null })
const saving      = ref(false)
const editError   = ref(null)
const editSuccess = ref(null)

// ── GPS 表示ヘルパー（knowledge があればそちらを優先）────────
function displayLat(loc) {
  return loc.has_knowledge && loc.knowledge_gps_lat != null ? loc.knowledge_gps_lat : loc.gps_lat
}
function displayLon(loc) {
  return loc.has_knowledge && loc.knowledge_gps_lon != null ? loc.knowledge_gps_lon : loc.gps_lon
}

// HTML エスケープ（Leaflet bindPopup 用）
function escapeHtml(s) {
  if (s == null) return ''
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

// ── Leaflet マップ ──────────────────────────────────────────
let leafletMap   = null
let markerLayer  = null
let editLeafletMap = null
let editMarker = null

function initMap() {
  const L = window.L
  if (!L || leafletMap) return
  leafletMap = L.map('locations-map', { zoomControl: true }).setView([26.5, 127.9], 9)
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(leafletMap)
}

function updateMap() {
  const L = window.L
  if (!L || !leafletMap) return

  if (markerLayer) leafletMap.removeLayer(markerLayer)
  markerLayer = L.layerGroup()

  locations.value.forEach(loc => {
    const lat = displayLat(loc)
    const lon = displayLon(loc)
    if (lat == null || lon == null) return

    const marker = L.circleMarker([lat, lon], {
      radius: 10 + Math.min(loc.dive_count * 2, 20),
      fillColor: loc.has_knowledge ? '#00b894' : '#00b4d8',
      color: '#fff',
      weight: 2,
      opacity: 1,
      fillOpacity: 0.75,
    })
    // Leaflet の bindPopup は HTML 評価。ロケーション名はユーザ制御できる文字列なので
    // 必ずエスケープする（CSP に依存しない多層防御）。
    marker.bindPopup(
      `<strong>${escapeHtml(loc.name)}</strong><br>${Number(loc.dive_count) || 0} ダイブ` +
      (loc.has_knowledge ? '<br><span class="text-success">✓ GPS 登録済</span>' : ''),
    )
    marker.on('click', () => openEdit(loc))
    marker.addTo(markerLayer)
  })

  markerLayer.addTo(leafletMap)
}

function flyToLocation(loc) {
  const L = window.L
  const lat = displayLat(loc)
  const lon = displayLon(loc)
  if (!leafletMap || !L || lat == null || lon == null) return
  leafletMap.flyTo([lat, lon], 13, { duration: 0.8 })
}

// ── データ取得 ──────────────────────────────────────────────
async function loadLocations() {
  loading.value = true
  error.value   = null
  try {
    const data = await fetchLocations()
    locations.value = data.locations ?? []
    updateMap()
  } catch (e) {
    console.error('fetchLocations failed:', e)
    error.value = 'データの取得に失敗しました。'
  } finally {
    loading.value = false
  }
}

// ── 編集モーダル ────────────────────────────────────────────
function openEdit(loc) {
  editTarget.value  = loc
  editError.value   = null
  editSuccess.value = null
  editForm.value = {
    canonical_name: loc.name,
    gps_lat: displayLat(loc) ?? null,
    gps_lon: displayLon(loc) ?? null,
  }
  flyToLocation(loc)
  nextTick(() => {
    initEditMap()
  })
}

function closeEdit() {
  destroyEditMap()
  editTarget.value  = null
  editError.value   = null
  editSuccess.value = null
}

function setEditCoordinates(lat, lon) {
  editForm.value.gps_lat = Number(lat.toFixed(6))
  editForm.value.gps_lon = Number(lon.toFixed(6))
}

function upsertEditMarker(lat, lon) {
  const L = window.L
  if (!L || !editLeafletMap) return
  if (!editMarker) {
    editMarker = L.marker([lat, lon], { draggable: true }).addTo(editLeafletMap)
    editMarker.on('dragend', () => {
      const { lat: markerLat, lng: markerLon } = editMarker.getLatLng()
      setEditCoordinates(markerLat, markerLon)
    })
    return
  }
  editMarker.setLatLng([lat, lon])
}

function syncEditMapFromForm() {
  const lat = Number(editForm.value.gps_lat)
  const lon = Number(editForm.value.gps_lon)
  if (!editLeafletMap || isNaN(lat) || isNaN(lon)) return
  if (lat < -90 || lat > 90 || lon < -180 || lon > 180) return
  upsertEditMarker(lat, lon)
  editLeafletMap.setView([lat, lon], Math.max(editLeafletMap.getZoom(), 13))
}

function initEditMap() {
  const L = window.L
  if (!L || !editTarget.value) return

  const lat = Number(editForm.value.gps_lat)
  const lon = Number(editForm.value.gps_lon)
  const hasGps = !isNaN(lat) && !isNaN(lon) && lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180
  const center = hasGps ? [lat, lon] : [26.5, 127.9]
  const zoom = hasGps ? 13 : 9

  if (!editLeafletMap) {
    editLeafletMap = L.map('edit-location-map', { zoomControl: true }).setView(center, zoom)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(editLeafletMap)
    editLeafletMap.on('click', (ev) => {
      const { lat: clickLat, lng: clickLon } = ev.latlng
      setEditCoordinates(clickLat, clickLon)
      upsertEditMarker(clickLat, clickLon)
    })
  } else {
    editLeafletMap.setView(center, zoom)
  }

  editLeafletMap.invalidateSize()
  if (hasGps) {
    upsertEditMarker(lat, lon)
  }
}

function destroyEditMap() {
  if (editMarker && editLeafletMap) {
    editLeafletMap.removeLayer(editMarker)
    editMarker = null
  }
  if (editLeafletMap) {
    editLeafletMap.remove()
    editLeafletMap = null
  }
}

async function saveEdit() {
  editError.value   = null
  editSuccess.value = null

  const lat = Number(editForm.value.gps_lat)
  const lon = Number(editForm.value.gps_lon)
  if (!editForm.value.canonical_name.trim()) {
    editError.value = 'ロケーション名を入力してください。'
    return
  }
  if (isNaN(lat) || lat < -90 || lat > 90) {
    editError.value = '緯度は -90 〜 90 の範囲で入力してください。'
    return
  }
  if (isNaN(lon) || lon < -180 || lon > 180) {
    editError.value = '経度は -180 〜 180 の範囲で入力してください。'
    return
  }

  saving.value = true
  try {
    const result = await updateLocationKnowledge(editTarget.value.normalized_name, {
      canonical_name: editForm.value.canonical_name.trim(),
      gps_lat: lat,
      gps_lon: lon,
    })
    editSuccess.value = `保存しました（${result.dives_updated ?? 0} 件のダイブログを更新）`
    // ローカル状態を更新してマップを再描画
    const target = locations.value.find(l => l.normalized_name === editTarget.value.normalized_name)
    if (target) {
      target.name             = editForm.value.canonical_name.trim()
      target.has_knowledge    = true
      target.knowledge_gps_lat = lat
      target.knowledge_gps_lon = lon
    }
    updateMap()
  } catch (e) {
    editError.value = e.message || '保存に失敗しました。'
  } finally {
    saving.value = false
  }
}

// ── ライフサイクル ──────────────────────────────────────────
onMounted(async () => {
  initMap()
  await loadLocations()
})

onBeforeUnmount(() => {
  if (markerLayer && leafletMap) {
    leafletMap.removeLayer(markerLayer)
    markerLayer = null
  }
  if (leafletMap) {
    leafletMap.remove()
    leafletMap = null
  }
  destroyEditMap()
})
</script>

<style scoped>
/* ── ロケーション行 ────────────────────────────────────────── */
.location-row {
  display: block;
  padding: 0.85rem 1.25rem;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  cursor: pointer;
  transition: background 0.15s;
}
.location-row:last-child {
  border-bottom: none;
}
.location-row:hover {
  background: rgba(0, 180, 216, 0.07);
}

/* ── ロケーションアイコン ──────────────────────────────────── */
.location-icon {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--ocean-teal, #00b4d8), var(--ocean-mid, #1a5f8a));
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1rem;
  flex-shrink: 0;
}

/* ── モーダルオーバーレイ ──────────────────────────────────── */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 2000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
}

/* ── 編集パネル ────────────────────────────────────────────── */
.edit-panel {
  background: #fff;
  border-radius: 14px;
  padding: 1.5rem;
  width: 100%;
  max-width: 420px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
}

.edit-map-container {
  width: 100%;
  height: 220px;
  border-radius: 10px;
  border: 1px solid rgba(0, 0, 0, 0.12);
}
</style>
