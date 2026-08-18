<template>
  <div class="container py-4">
    <div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
      <div>
        <div class="text-muted small text-uppercase fw-semibold tracking">Analysis</div>
        <h3 class="mb-0">過去ダイブログ分析レポート</h3>
      </div>
      <div class="d-flex align-items-center gap-2 flex-wrap justify-content-end">
        <span class="badge bg-primary rounded-pill px-3 py-2">{{ dives.length }} 件</span>
        <button class="btn btn-primary" :disabled="generating || !dives.length" @click="regenerateReport">
          <span v-if="generating" class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>
          <i v-else class="bi bi-stars me-2"></i>
          {{ generating ? 'AIで作成中' : 'レポートの作り直し' }}
        </button>
      </div>
    </div>

    <div v-if="loading" class="text-center py-5">
      <LoadingIndicator />
    </div>

    <div v-else-if="error" class="alert alert-danger">{{ error }}</div>

    <div v-else class="analysis-wrapper">
      <div v-if="aiError" class="alert alert-danger mb-0">{{ aiError }}</div>
      <div v-if="aiReport" class="generated-meta">
        <i class="bi bi-cpu me-1"></i>{{ aiReport.model_deployment }} / {{ formatGeneratedAt(aiReport.generated_at) }} 作成
      </div>

      <div class="row g-3 mb-4">
        <div class="col-md-4">
          <div class="report-card h-100">
            <div class="label">最深水深</div>
            <div class="metric">{{ maxDepthLabel }}</div>
            <div class="meta">
              <router-link v-if="maxDepthDive" :to="`/dive/${maxDepthDive.dive_id}`" class="link-primary text-decoration-none">
                {{ maxDepthDive.location?.name || 'ロケーション未登録' }} / {{ formatDateTime(maxDepthDive.dive_info?.datetime) }}
              </router-link>
            </div>
          </div>
        </div>

        <div class="col-md-4">
          <div class="report-card h-100">
            <div class="label">最低水温</div>
            <div class="metric">{{ minTempLabel }}</div>
            <div class="meta">
              <router-link v-if="minTempDive" :to="`/dive/${minTempDive.dive_id}`" class="link-primary text-decoration-none">
                {{ minTempDive.location?.name || 'ロケーション未登録' }} / {{ formatDateTime(minTempDive.dive_info?.datetime) }}
              </router-link>
            </div>
          </div>
        </div>

        <div class="col-md-4">
          <div class="report-card h-100">
            <div class="label">最長潜水時間</div>
            <div class="metric">{{ maxDurationLabel }}</div>
            <div class="meta">
              <router-link v-if="maxDurationDive" :to="`/dive/${maxDurationDive.dive_id}`" class="link-primary text-decoration-none">
                {{ maxDurationDive.location?.name || 'ロケーション未登録' }} / {{ formatDateTime(maxDurationDive.dive_info?.datetime) }}
              </router-link>
            </div>
          </div>
        </div>
      </div>

      <div class="row g-4 mb-4">
        <div class="col-lg-6">
          <div class="chart-card h-100">
            <div class="section-title">エリア別潜水本数</div>
            <div class="chart-wrap chart-clickable"><canvas ref="areaChartRef"></canvas></div>
          </div>
        </div>
        <div class="col-lg-6">
          <div class="chart-card h-100">
            <div class="section-title">月別潜水本数</div>
            <div class="chart-wrap"><canvas ref="monthChartRef"></canvas></div>
          </div>
        </div>
      </div>

      <div v-if="selectedArea" class="report-card mb-4">
        <div class="selected-area-header">
          <div>
            <div class="section-title mb-1">{{ selectedArea }} のダイブログ</div>
            <div class="text-muted small">{{ selectedAreaDives.length }} 件</div>
          </div>
          <button class="btn btn-sm btn-outline-secondary" type="button" title="一覧を閉じる" @click="selectedArea = ''">
            <i class="bi bi-x-lg" aria-hidden="true"></i>
            <span class="visually-hidden">一覧を閉じる</span>
          </button>
        </div>
        <div class="selected-dive-list">
          <router-link
            v-for="dive in selectedAreaDives"
            :key="dive.dive_id"
            :to="`/dive/${dive.dive_id}`"
            class="selected-dive-item"
          >
            <span class="selected-dive-date">{{ formatDateTime(dive.dive_info?.datetime) }}</span>
            <span class="selected-dive-location">{{ dive.location?.name || 'ロケーション未登録' }}</span>
            <i class="bi bi-chevron-right" aria-hidden="true"></i>
          </router-link>
        </div>
      </div>

      <div class="row g-4 mb-4">
        <div class="col-lg-6">
          <div class="report-card h-100">
            <div class="section-title">各エリアでの潜り方傾向</div>
            <div v-if="aiReport" class="area-list">
              <div v-for="area in aiReport.area_trends" :key="area.area" class="area-item">
                <div class="area-title">{{ area.area }}</div>
                <div class="area-summary">{{ area.summary }}</div>
                <div class="area-meta mt-2"><i class="bi bi-database me-1"></i>{{ area.evidence }}</div>
              </div>
            </div>
            <div v-else class="ai-placeholder">「レポートの作り直し」を押すと、Microsoft Foundry が全ログから分析します。</div>
          </div>
        </div>

        <div class="col-lg-6">
          <div class="report-card h-100">
            <div class="section-title">対象ユーザの潜り方傾向分析</div>
            <p v-if="aiReport" class="user-trend mb-0">{{ aiReport.user_trend }}</p>
            <div v-else class="ai-placeholder">まだ AI レポートは作成されていません。</div>
          </div>
        </div>
      </div>

      <div class="report-card mb-4">
        <div class="section-title">おすすめダイビングスポット</div>
        <div v-if="aiReport" class="recommend-list">
          <div v-for="item in aiReport.recommendations" :key="`${item.country_or_region}:${item.spot}`" class="recommend-item">
            <div class="recommend-badge" :class="item.visited ? 'is-rated' : 'is-new'">
              {{ item.visited ? '訪問済み' : '未訪問候補' }}
            </div>
            <div class="recommend-body">
              <div class="recommend-name">{{ item.spot }} <span class="text-muted fw-normal small">{{ item.country_or_region }}</span></div>
              <div class="recommend-meta">適合度 {{ formatMatchScore(item.match_score) }} / 5 · {{ item.reason }}</div>
            </div>
          </div>
        </div>
        <div v-else class="ai-placeholder">評価傾向に基づく国内外の候補を AI が提案します。</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, nextTick, onMounted } from 'vue'
import { Chart, BarController, BarElement, CategoryScale, LinearScale, Tooltip, Legend } from 'chart.js'
import { fetchAnalysisReport, fetchDives, generateAnalysisReport } from '../api/dives.js'
import LoadingIndicator from '../components/LoadingIndicator.vue'

Chart.register(BarController, BarElement, CategoryScale, LinearScale, Tooltip, Legend)

const dives = ref([])
const loading = ref(true)
const error = ref('')
const generating = ref(false)
const aiError = ref('')
const aiReport = ref(null)
const areaChartRef = ref(null)
const monthChartRef = ref(null)
const selectedArea = ref('')
const selectedAreaDives = computed(() =>
  dives.value.filter((dive) => getArea(dive.location?.name) === selectedArea.value)
)

const maxDepthLabel = ref('—')
const minTempLabel = ref('—')
const maxDurationLabel = ref('—')
const maxDepthDive = ref(null)
const minTempDive = ref(null)
const maxDurationDive = ref(null)

function formatNumber(value, digits = 1) {
  if (value == null || Number.isNaN(Number(value))) return '—'
  return Number(value).toFixed(digits)
}

function positiveNumber(value) {
  const number = Number(value)
  return Number.isFinite(number) && number > 0 ? number : null
}

function waterTemperature(dive) {
  return positiveNumber(dive.location?.water_min_temp_c)
    ?? positiveNumber(dive.location?.surface_temp_c)
}

function formatDateTime(dt) {
  if (!dt) return '—'
  const d = new Date(dt)
  if (Number.isNaN(d.getTime())) return dt
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日 ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function formatGeneratedAt(dt) {
  if (!dt) return '—'
  return new Intl.DateTimeFormat('ja-JP', {
    year: 'numeric', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit',
  }).format(new Date(dt))
}

function formatMatchScore(score) {
  return Math.max(0, Math.min(5, Number(score) || 0)).toFixed(1)
}

function getArea(name) {
  const source = String(name || '').trim()
  const separatorIndexes = [source.indexOf(':'), source.indexOf('：')].filter((index) => index >= 0)
  if (!separatorIndexes.length) return '不明'
  return source.slice(0, Math.min(...separatorIndexes)).trim() || '不明'
}

function buildChart(canvas, labels, data, color, onBarClick = null) {
  if (!canvas || !labels.length) return
  // Chart.js の重複生成を避ける
  if (canvas.__chart) canvas.__chart.destroy()

  canvas.__chart = new Chart(canvas, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: '件数',
        data,
        backgroundColor: color,
        borderRadius: 8,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { displayColors: false },
      },
      onClick: onBarClick
        ? (_event, elements) => {
            const index = elements[0]?.index
            if (index != null) onBarClick(labels[index])
          }
        : undefined,
      onHover: onBarClick
        ? (event, elements) => {
            event.native.target.style.cursor = elements.length ? 'pointer' : 'default'
          }
        : undefined,
      scales: {
        y: {
          beginAtZero: true,
          ticks: { precision: 0 },
        },
      },
    },
  })
}

function aggregateData() {
  const diveList = dives.value || []

  if (!diveList.length) return

  const maxDepthEntry = diveList.reduce((best, dive) => {
    const value = positiveNumber(dive.dive_info?.max_depth_m)
    if (value === null) return best
    if (!best || value > positiveNumber(best.dive_info?.max_depth_m)) return dive
    return best
  }, null)
  maxDepthDive.value = maxDepthEntry
  if (maxDepthEntry) {
    maxDepthLabel.value = `${formatNumber(maxDepthEntry.dive_info?.max_depth_m, 1)} m`
  }

  const minTempEntry = diveList.reduce((best, dive) => {
    const value = waterTemperature(dive)
    if (value === null) return best
    if (!best) return dive
    const current = waterTemperature(best)
    return value < current ? dive : best
  }, null)
  minTempDive.value = minTempEntry
  if (minTempEntry) {
    minTempLabel.value = `${formatNumber(waterTemperature(minTempEntry), 1)} ℃`
  }

  const maxDurationEntry = diveList.reduce((best, dive) => {
    const value = positiveNumber(dive.dive_info?.dive_time_min)
    if (value === null) return best
    if (!best || value > positiveNumber(best.dive_info?.dive_time_min)) return dive
    return best
  }, null)
  maxDurationDive.value = maxDurationEntry
  if (maxDurationEntry) {
    maxDurationLabel.value = `${formatNumber(maxDurationEntry.dive_info?.dive_time_min, 1)} 分`
  }

  const areaMap = new Map()
  diveList.forEach((dive) => {
    const key = getArea(dive.location?.name)
    areaMap.set(key, (areaMap.get(key) || 0) + 1)
  })
  const areaEntries = [...areaMap.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8)
  buildChart(
    areaChartRef.value,
    areaEntries.map(([name]) => name),
    areaEntries.map(([, count]) => count),
    '#0ea5e9',
    (area) => { selectedArea.value = area },
  )

  const monthMap = new Map(Array.from({ length: 12 }, (_, i) => [i + 1, 0]))
  diveList.forEach((dive) => {
    const date = new Date(dive.dive_info?.datetime || 0)
    if (Number.isNaN(date.getTime())) return
    const month = date.getMonth() + 1
    monthMap.set(month, (monthMap.get(month) || 0) + 1)
  })
  const monthEntries = [...monthMap.entries()].map(([month, count]) => ({ month, count }))
  buildChart(monthChartRef.value, monthEntries.map((entry) => `${entry.month}月`), monthEntries.map((entry) => entry.count), '#14b8a6')

}

async function regenerateReport() {
  generating.value = true
  aiError.value = ''
  try {
    aiReport.value = await generateAnalysisReport()
  } catch (e) {
    aiError.value = e.message || 'AI レポートの生成に失敗しました。'
  } finally {
    generating.value = false
  }
}

async function loadReport() {
  loading.value = true
  error.value = ''
  try {
    const data = await fetchDives({})
    dives.value = data.dives || []
  } catch (e) {
    error.value = 'データの取得に失敗しました。バックエンドの状態を確認してください。'
  }
  if (!error.value) {
    try {
      aiReport.value = await fetchAnalysisReport()
    } catch (e) {
      aiError.value = e.message || '保存済みレポートの取得に失敗しました。'
    }
    loading.value = false
    await nextTick()
    aggregateData()
    return
  }
  loading.value = false
}

onMounted(() => {
  loadReport()
})
</script>

<style scoped>
.analysis-wrapper {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.tracking {
  letter-spacing: 0.12em;
}

.generated-meta {
  color: #64748b;
  font-size: 0.82rem;
  text-align: right;
}

.report-card,
.chart-card {
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 3px 14px rgba(15, 23, 42, 0.06);
  padding: 1.25rem;
}

.label {
  color: #0ea5e9;
  font-weight: 700;
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 0.65rem;
}

.metric {
  font-size: clamp(1.4rem, 2vw, 2.2rem);
  font-weight: 800;
  line-height: 1.2;
  margin-bottom: 0.4rem;
  color: #0f172a;
}

.meta {
  color: #475569;
  font-size: 0.9rem;
  line-height: 1.5;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-weight: 700;
  color: #0f172a;
  margin-bottom: 1rem;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid #e2e8f0;
}

.selected-area-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
}

.selected-dive-list {
  display: grid;
  gap: 0.5rem;
}

.selected-dive-item {
  display: grid;
  grid-template-columns: minmax(10rem, 0.7fr) minmax(0, 1.3fr) auto;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 0.85rem;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  color: #0f172a;
  text-decoration: none;
}

.selected-dive-item:hover,
.selected-dive-item:focus-visible {
  border-color: #0ea5e9;
  background: #f0f9ff;
}

.selected-dive-date {
  font-weight: 700;
}

.selected-dive-location {
  min-width: 0;
  overflow-wrap: anywhere;
  color: #475569;
}

.chart-wrap {
  position: relative;
  height: 320px;
}

@media (max-width: 575.98px) {
  .selected-dive-item {
    grid-template-columns: minmax(0, 1fr) auto;
  }

  .selected-dive-location {
    grid-column: 1 / -1;
    grid-row: 2;
  }
}

.area-list,
.recommend-list {
  display: flex;
  flex-direction: column;
  gap: 0.9rem;
}

.area-item,
.recommend-item {
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 0.8rem 0.9rem;
  background: linear-gradient(180deg, #f8fbff, #ffffff);
}

.area-title,
.recommend-name {
  font-weight: 700;
  color: #0f172a;
  margin-bottom: 0.2rem;
}

.area-meta,
.recommend-meta {
  color: #475569;
  font-size: 0.88rem;
  line-height: 1.5;
}

.area-summary {
  margin-top: 0.4rem;
  color: #0f172a;
  font-size: 0.9rem;
}

.user-trend {
  color: #0f172a;
  line-height: 1.9;
  white-space: pre-wrap;
}

.ai-placeholder {
  border: 1px dashed #94a3b8;
  border-radius: 10px;
  padding: 1rem;
  color: #64748b;
  background: #f8fafc;
}

.insight-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.9rem;
}

.insight-row {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 0.75rem 0.85rem;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.insight-row.full {
  grid-column: 1 / -1;
}

.insight-label {
  color: #64748b;
  font-size: 0.8rem;
}

.recommend-item {
  display: flex;
  align-items: flex-start;
  gap: 0.8rem;
}

.recommend-badge {
  min-width: 92px;
  text-align: center;
  padding: 0.35rem 0.6rem;
  border-radius: 999px;
  font-size: 0.72rem;
  font-weight: 700;
  color: white;
}

.recommend-badge.is-rated { background: #0ea5e9; }
.recommend-badge.is-new { background: #14b8a6; }
.recommend-badge.is-foreign { background: #8b5cf6; }
.recommend-badge.is-local { background: #f59e0b; }

@media (max-width: 767.98px) {
  .insight-grid {
    grid-template-columns: 1fr;
  }

  .recommend-item {
    flex-direction: column;
  }
}
</style>
