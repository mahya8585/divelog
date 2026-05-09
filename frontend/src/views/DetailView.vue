<template>
  <div class="container py-4">
    <!-- 戻るボタン -->
    <router-link to="/" class="btn-back mb-3 d-inline-block">
      <i class="bi bi-chevron-left"></i> 一覧に戻る
    </router-link>

    <!-- ローディング -->
    <div v-if="loading" class="text-center py-5">
      <LoadingIndicator />
    </div>

    <!-- 404 -->
    <div v-else-if="notFound" class="alert alert-warning">
      ダイブログが見つかりません。
    </div>

    <!-- エラー -->
    <div v-else-if="error" class="alert alert-danger">{{ error }}</div>

    <!-- 詳細コンテンツ -->
    <template v-else-if="dive">
      <!-- ヘッダー -->
      <div class="section-card mb-3 d-flex align-items-center gap-3">
        <div class="dive-number-circle fs-5">#{{ dive.dive_info.dive_number }}</div>
        <div>
          <h5 class="mb-1">{{ formatDt(dive.dive_info.datetime) }}</h5>
          <div class="text-muted small">
            <i class="bi bi-clock me-1"></i>終了 {{ endTime }}
          </div>
          <div class="text-muted small">
            <i class="bi bi-geo-alt-fill me-1"></i>{{ dive.location?.name || '—' }}
          </div>
          <div class="text-warning">{{ stars(dive.dive_info.rating) }}</div>
        </div>
      </div>

      <!-- スタットタイル -->
      <div class="row g-2 mb-3">
        <div class="col-6 col-md-3">
          <div class="stat-tile">
            <div class="stat-value">{{ fmtNum(dive.dive_info.max_depth_m, 1) }}</div>
            <div class="text-muted small">m</div>
            <div class="fw-semibold small">最大水深</div>
          </div>
        </div>
        <div class="col-6 col-md-3">
          <div class="stat-tile">
            <div class="stat-value">{{ Math.round(dive.dive_info.dive_time_min) }}</div>
            <div class="text-muted small">分</div>
            <div class="fw-semibold small">潜水時間</div>
          </div>
        </div>
        <div class="col-6 col-md-3">
          <div class="stat-tile">
            <div class="stat-value">{{ Math.round(dive.dive_info.surface_interval_min ?? 0) }}</div>
            <div class="text-muted small">分</div>
            <div class="fw-semibold small">水面休息</div>
          </div>
        </div>
        <div class="col-6 col-md-3">
          <div class="stat-tile">
            <div class="stat-value">{{ fmtNum(dive.dive_info.avg_depth_m, 1) }}</div>
            <div class="text-muted small">m</div>
            <div class="fw-semibold small">平均水深</div>
          </div>
        </div>
      </div>

      <!-- プロファイルチャート -->
      <div class="section-card mb-3">
        <div class="section-title"><i class="bi bi-graph-down me-1"></i>ダイブプロファイル</div>
        <div class="chart-container">
          <canvas ref="chartCanvas"></canvas>
        </div>
      </div>

      <!-- ロケーション + 水温 -->
      <div class="row g-3 mb-3">
        <div class="col-md-7">
          <div class="section-card h-100">
            <div class="section-title"><i class="bi bi-geo-alt me-1"></i>ロケーション</div>
            <div id="detail-map" class="map-container-sm rounded mb-2"></div>
            <div class="text-muted small">GPS: {{ dive.location?.gps_lat }}, {{ dive.location?.gps_lon }}</div>
          </div>
        </div>
        <div class="col-md-5">
          <div class="section-card h-100">
            <div class="section-title"><i class="bi bi-thermometer-half me-1"></i>気温・水温</div>
            <div class="gear-row"><span class="gear-label">気温</span>{{ fmtNum(dive.location?.air_temp_c, 1) }} ℃</div>
            <div class="gear-row"><span class="gear-label">水面水温</span>{{ fmtNum(dive.location?.surface_temp_c, 1) }} ℃</div>
            <div class="gear-row"><span class="gear-label">最低水温</span>{{ fmtNum(dive.location?.water_min_temp_c, 1) }} ℃</div>
            <div class="section-title mt-3"><i class="bi bi-shield-check me-1"></i>安全情報</div>
            <div class="gear-row"><span class="gear-label">デコ停止</span>{{ dive.dive_info.deco_required ? 'あり' : 'なし' }}</div>
            <div class="gear-row"><span class="gear-label">バイオレーション</span>{{ dive.dive_info.violation ? 'あり' : 'なし' }}</div>
          </div>
        </div>
      </div>

      <!-- タンク + ギア -->
      <div class="row g-3 mb-3">
        <div class="col-md-6">
          <div class="section-card">
            <div class="section-title"><i class="bi bi-capsule me-1"></i>タンク情報</div>
            <div class="gear-row"><span class="gear-label">FO2</span>{{ dive.equipment?.tank?.fo2_percent }} %</div>
            <div class="gear-row"><span class="gear-label">開始圧力</span>{{ fmtNum(dive.equipment?.tank?.start_pressure_bar) }} bar</div>
            <div class="gear-row"><span class="gear-label">終了圧力</span>{{ fmtNum(dive.equipment?.tank?.end_pressure_bar) }} bar</div>
          </div>
        </div>
        <div class="col-md-6">
          <div class="section-card">
            <div class="section-title"><i class="bi bi-person-gear me-1"></i>ギア</div>
            <div v-for="[label, key] in gearRows" :key="key" class="gear-row">
              <span class="gear-label">{{ label }}</span>{{ dive.equipment?.gear?.[key] || '—' }}
            </div>
          </div>
        </div>
      </div>

      <!-- ダイコン情報 -->
      <div class="section-card mb-3">
        <div class="section-title"><i class="bi bi-cpu me-1"></i>ダイブコンピュータ</div>
        <div class="row">
          <div class="col-6 col-md-3"><div class="gear-row"><span class="gear-label">メーカー</span>{{ dive.equipment?.computer?.manufacturer }}</div></div>
          <div class="col-6 col-md-3"><div class="gear-row"><span class="gear-label">モデル</span>{{ dive.equipment?.computer?.model }}</div></div>
          <div class="col-6 col-md-3"><div class="gear-row"><span class="gear-label">シリアル</span>{{ dive.equipment?.computer?.serial }}</div></div>
          <div class="col-6 col-md-3"><div class="gear-row"><span class="gear-label">ファームウェア</span>{{ dive.equipment?.computer?.firmware }}</div></div>
        </div>
      </div>

      <!-- メモ -->
      <div v-if="dive.memo" class="section-card mb-3">
        <div class="section-title"><i class="bi bi-journal-text me-1"></i>メモ</div>
        <!-- タグ -->
        <div v-if="tags.length" class="mb-2">
          <router-link
            v-for="tag in tags" :key="tag"
            :to="`/?tag=${encodeURIComponent(tag)}`"
            class="tag-badge"
          >#{{ tag }}</router-link>
        </div>
        <div class="memo-box" v-html="renderedMemo"></div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { Chart, LineController, LineElement, PointElement, LinearScale, CategoryScale, Tooltip, Legend, Filler } from 'chart.js'
import { fetchDive } from '../api/dives.js'
import LoadingIndicator from '../components/LoadingIndicator.vue'
import { escapeHtml } from '../utils/html.js'

Chart.register(LineController, LineElement, PointElement, LinearScale, CategoryScale, Tooltip, Legend, Filler)

const route    = useRoute()
const dive     = ref(null)
const tags     = ref([])
const loading  = ref(true)
const error    = ref(null)
const notFound = ref(false)
const chartCanvas = ref(null)

// ── ユーティリティ ─────────────────────────────────────
const WEEKDAYS = ['月', '火', '水', '木', '金', '土', '日']
function formatDt(dtStr) {
  if (!dtStr) return ''
  const dt  = new Date(dtStr)
  const dow = WEEKDAYS[dt.getDay() === 0 ? 6 : dt.getDay() - 1]
  const hh  = String(dt.getHours()).padStart(2, '0')
  const mm  = String(dt.getMinutes()).padStart(2, '0')
  return `${dt.getFullYear()}年${dt.getMonth() + 1}月${dt.getDate()}日（${dow}） ${hh}:${mm}`
}
function stars(rating) {
  const r = Math.max(0, Math.min(5, Number(rating) || 0))
  return '★'.repeat(r) + '☆'.repeat(5 - r)
}
function fmtNum(val, digits = 0) {
  if (val == null || val === '') return '—'
  return Number(val).toFixed(digits)
}

const endTime = computed(() => {
  if (!dive.value?.dive_info?.datetime || !dive.value?.dive_info?.dive_time_min) return '—'
  const start = new Date(dive.value.dive_info.datetime)
  const end   = new Date(start.getTime() + dive.value.dive_info.dive_time_min * 60 * 1000)
  const hh = String(end.getHours()).padStart(2, '0')
  const mm = String(end.getMinutes()).padStart(2, '0')
  return `${hh}:${mm}`
})

// ── ギア行定義 ────────────────────────────────────────
const gearRows = [
  ['氏名', 'name'], ['ウェイト', 'weight_belt_kg'], ['レギュレーター', 'regulator'],
  ['BC', 'bc'], ['スーツ', 'suit'], ['ブーツ', 'boots'],
  ['グローブ', 'gloves'], ['フード', 'hood'], ['マスク', 'mask'],
  ['スノーケル', 'snorkel'], ['フィン', 'fins'],
]

// ── メモレンダリング ───────────────────────────────────
const renderedMemo = computed(() => {
  if (!dive.value?.memo) return ''
  // XSS 対策: HTML エスケープしてから #tag を変換
  const escaped = dive.value.memo
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
  return escaped
    .replace(/#(\S+)/g, (_, t) => `<a href="/?tag=${encodeURIComponent(t)}" class="tag-badge">#${t}</a>`)
    .replace(/\n/g, '<br>')
})

// ── Chart.js プロファイルチャート ──────────────────────
function buildChart(profile) {
  if (!chartCanvas.value || !profile?.length) return

  const labels = profile.map(p => p.time_min.toFixed(1))
  const depths = profile.map(p => p.depth_m)
  const temps  = profile.map(p => p.temp_c ?? null)
  const hasTemp = temps.some(t => t !== null)

  const datasets = [
    {
      label: '水深 (m)', data: depths,
      borderColor: '#0096c7', backgroundColor: 'rgba(0,150,199,.15)',
      fill: true, tension: 0.3, pointRadius: 0, borderWidth: 2,
      yAxisID: 'yDepth',
    },
  ]
  if (hasTemp) {
    datasets.push({
      label: '水温 (℃)', data: temps,
      borderColor: '#ff6b6b', backgroundColor: 'transparent',
      fill: false, tension: 0.3, pointRadius: 0, borderWidth: 1.5,
      spanGaps: true, yAxisID: 'yTemp',
    })
  }

  new Chart(chartCanvas.value, {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: hasTemp } },
      scales: {
        x: {
          ticks: { maxTicksLimit: 8, font: { size: 10 } },
          title: { display: true, text: '経過時間 (分)', font: { size: 10 } },
        },
        yDepth: {
          reverse: true, position: 'left',
          title: { display: true, text: '水深 (m)', font: { size: 10 } },
          ticks: { font: { size: 10 } },
        },
        ...(hasTemp ? {
          yTemp: {
            position: 'right',
            title: { display: true, text: '水温 (℃)', font: { size: 10 } },
            ticks: { font: { size: 10 } },
            grid: { drawOnChartArea: false },
          },
        } : {}),
      },
    },
  })
}

// ── Leaflet 詳細マップ ────────────────────────────────
function buildMap(lat, lon, name) {
  const L = window.L
  if (!L || lat == null || lon == null) return
  const map = L.map('detail-map').setView([lat, lon], 14)
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map)
  const icon = L.divIcon({ html: '🤿', className: '', iconSize: [28, 28], iconAnchor: [14, 14] })
  L.marker([lat, lon], { icon }).bindPopup(`<strong>${escapeHtml(name || '')}</strong>`).openPopup().addTo(map)
}

// ── マウント ──────────────────────────────────────────
onMounted(async () => {
  const diveId = route.params.id
  try {
    const data = await fetchDive(diveId)
    dive.value = data.dive
    tags.value = data.tags || []
    // DOM レンダリング後にチャート・マップを初期化
    setTimeout(() => {
      buildChart(dive.value.profile)
      const loc = dive.value.location || {}
      buildMap(loc.gps_lat, loc.gps_lon, loc.name)
    }, 0)
  } catch (e) {
    if (e.message === 'NOT_FOUND') notFound.value = true
    else error.value = 'データの取得に失敗しました。'
  } finally {
    loading.value = false
  }
})
</script>
