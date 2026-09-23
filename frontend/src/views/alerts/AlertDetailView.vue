<template>
  <div class="page-container workbench" v-loading="loading">
    <!-- 告警概要 -->
    <el-card shadow="never">
      <div class="alert-head">
        <div class="alert-head-main">
          <div class="alert-title-row">
            <el-button :icon="ArrowLeft" link @click="$router.push('/alerts')">返回列表</el-button>
            <el-tag :type="severityTag(alert.severity)" size="small">{{ alert.severity || '未分级' }}</el-tag>
            <el-tag :type="alertTag(alert.status).type" size="small">{{ alertTag(alert.status).label }}</el-tag>
            <el-tag :type="analysisTag(alert.analysis_status).type" size="small" effect="plain">
              {{ analysisTag(alert.analysis_status).label }}
            </el-tag>
          </div>
          <h2 class="alert-title">{{ alert.title || '（无标题）' }}</h2>
          <div class="alert-meta">
            <span><el-icon><Monitor /></el-icon> 主机：<b>{{ alert.host || '-' }}</b></span>
            <span>事件 ID：<span class="mono">{{ alert.event_id }}</span></span>
            <span>发生：{{ fmtTime(alert.occurred_at) }}</span>
            <span v-if="alert.recovered_at">恢复：{{ fmtTime(alert.recovered_at) }}</span>
            <span v-if="alert.analysis_times">分析次数：{{ alert.analysis_times }}</span>
          </div>
          <div v-if="alert.analysis_error" class="analysis-error">
            <el-icon><WarningFilled /></el-icon> 上次分析失败：{{ alert.analysis_error }}
          </div>
        </div>
        <div class="alert-head-actions">
          <el-button type="primary" :icon="MagicStick" :loading="analyzing"
                     @click="runAnalyze">
            {{ alert.analysis_status === 'pending' ? '立即分析' : '重新分析' }}
          </el-button>
          <el-button :icon="Download" :disabled="!alert.report" @click="exportReport">导出报告</el-button>
          <el-button type="success" :icon="Promotion" :disabled="!alert.report"
                     @click="openNotify">推送通知</el-button>
        </div>
      </div>
    </el-card>

    <el-row :gutter="14">
      <!-- 左：指标 + 日志 -->
      <el-col :xs="24" :md="15">
        <el-card ref="metricCard" shadow="never" class="panel">
          <div class="panel-title">
            <el-icon><TrendCharts /></el-icon> 指标趋势（告警时刻前后窗口）
          </div>
          <template v-if="series.length">
            <div class="series-chips">
              <el-checkbox-group v-model="visibleSeries" size="small">
                <el-checkbox-button v-for="s in series" :key="s.item_id" :label="s.item_id">
                  {{ s.name }}
                </el-checkbox-button>
              </el-checkbox-group>
            </div>
            <EChart :option="chartOption" height="300px" />
            <el-table :data="seriesStats" size="small" style="margin-top:8px">
              <el-table-column prop="name" label="监控项" min-width="130" show-overflow-tooltip />
              <el-table-column label="均值" width="80"><template #default="{ row }">{{ row.stats.avg }}{{ row.units }}</template></el-table-column>
              <el-table-column label="峰值" width="80"><template #default="{ row }">{{ row.stats.max }}{{ row.units }}</template></el-table-column>
              <el-table-column label="末值" width="80"><template #default="{ row }">{{ row.stats.last }}{{ row.units }}</template></el-table-column>
              <el-table-column label="窗口变化" width="90">
                <template #default="{ row }">
                  <span :style="{ color: changeColor(row.stats.change_pct) }">
                    {{ row.stats.change_pct == null ? '-' : `${row.stats.change_pct > 0 ? '+' : ''}${row.stats.change_pct}%` }}
                  </span>
                </template>
              </el-table-column>
            </el-table>
          </template>
          <el-empty v-else-if="!metricCtx.available" :description="metricCtx.reason || '无指标证据'" :image-size="70" />
          <el-empty v-else description="窗口内未取到相关监控项数据" :image-size="70" />
        </el-card>

        <el-card shadow="never" class="panel">
          <div class="panel-title">
            <el-icon><Tickets /></el-icon> 关联日志
            <el-tag v-for="p in logPlatforms" :key="p.provider" size="small" effect="plain" style="margin-left:6px">
              {{ p.provider }} ×{{ p.count }}
            </el-tag>
            <span v-if="!logPlatforms.length" class="text-muted">（无日志证据）</span>
          </div>
          <el-table v-if="logs.length" :data="logs" size="small" height="380" row-key="_idx">
            <el-table-column label="时间" width="150">
              <template #default="{ row }">{{ row.timestamp || fmtTime(row.ts * 1000) }}</template>
            </el-table-column>
            <el-table-column label="级别" width="76">
              <template #default="{ row }">
                <el-tag size="small" :type="logLevelType(row.level)" effect="plain">{{ row.level || '-' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="host" label="主机" width="110" show-overflow-tooltip />
            <el-table-column prop="message" label="日志内容" min-width="240" show-overflow-tooltip />
          </el-table>
          <el-empty v-else description="窗口内未检索到关联日志" :image-size="70" />
        </el-card>
      </el-col>

      <!-- 右：AI 结论 + 证据 + 通知 -->
      <el-col :xs="24" :md="9">
        <el-card shadow="never" class="panel">
          <div class="panel-title">
            <el-icon color="var(--el-color-primary)"><MagicStick /></el-icon> AI 根因分析
            <el-tag v-if="report" size="small" type="info" effect="plain" style="margin-left:auto">
              {{ report.provider }}/{{ report.model }}
            </el-tag>
          </div>
          <template v-if="report">
            <el-alert v-if="report.degraded_from" type="warning" :closable="false" show-icon
                      :title="`主供应商 ${report.degraded_from} 不可用，已由 ${report.provider} 降级完成`"
                      style="margin-bottom:10px" />
            <template v-if="result.root_causes?.length">
              <div v-for="(c, i) in result.root_causes" :key="i" class="cause-item">
                <div class="cause-head">
                  <el-tag size="small" :type="confidenceType(c.confidence)">置信度 {{ c.confidence || '?' }}</el-tag>
                  <b>{{ c.cause || c }}</b>
                </div>
                <div v-if="c.reason" class="text-muted cause-reason">依据：{{ c.reason }}</div>
              </div>
            </template>
            <el-empty v-else description="模型未给出根因" :image-size="50" />

            <el-divider content-position="left">证据链（点击定位）</el-divider>
            <div v-if="result.evidence?.length" class="evidence-list">
              <div v-for="(e, i) in result.evidence" :key="i" class="evidence-line"
                   :class="{ active: activeEvidence === i }"
                   @click="locate(e)">
                <el-tag size="small" :type="e.type === 'metric' ? 'warning' : 'primary'" effect="plain" style="margin-right:6px">
                  {{ e.type || '-' }}
                </el-tag>
                <span class="evidence-ref mono">{{ e.ref || '' }}</span>
                <div class="text-muted evidence-summary">{{ e.summary || e }}</div>
              </div>
            </div>
            <div v-else class="text-muted">无</div>

            <el-divider content-position="left">影响范围</el-divider>
            <div class="section-text">{{ result.impact || '未评估' }}</div>

            <el-divider content-position="left">处置建议</el-divider>
            <ol v-if="result.remediation?.length" class="step-list">
              <li v-for="(s, i) in result.remediation" :key="i">{{ typeof s === 'string' ? s : s.step }}</li>
            </ol>
            <div v-else class="text-muted">无</div>

            <el-divider content-position="left">预防建议</el-divider>
            <ol v-if="result.prevention?.length" class="step-list">
              <li v-for="(s, i) in result.prevention" :key="i">{{ typeof s === 'string' ? s : s.step }}</li>
            </ol>
            <div v-else class="text-muted">无</div>
          </template>
          <el-empty v-else-if="alert.analysis_status === 'processing'" description="正在分析中，请稍候…" :image-size="70" />
          <el-empty v-else description="尚未生成分析报告，点击右上角「立即分析」" :image-size="70" />
        </el-card>

        <el-card shadow="never" class="panel">
          <div class="panel-title"><el-icon><Promotion /></el-icon> 通知投递记录</div>
          <el-timeline v-if="notifications.length">
            <el-timeline-item v-for="n in notifications" :key="n.id"
                              :type="n.success ? 'success' : 'danger'"
                              :timestamp="fmtTime(n.sent_at)" placement="top">
              <el-tag size="small" :type="n.success ? 'success' : 'danger'" effect="plain" style="margin-right:6px">
                {{ n.success ? '成功' : '失败' }}
              </el-tag>
              <span class="mono">{{ n.channel }}</span>
              <span class="text-muted" style="margin-left:6px">{{ n.trigger_type === 'auto' ? '自动' : '手动' }}</span>
              <div v-if="n.response" class="text-muted notify-resp">{{ n.response }}</div>
            </el-timeline-item>
          </el-timeline>
          <el-empty v-else description="暂无推送记录" :image-size="50" />
        </el-card>
      </el-col>
    </el-row>

    <!-- 推送对话框 -->
    <el-dialog v-model="notifyVisible" title="推送分析报告" width="420px">
      <el-checkbox-group v-model="notifyChannels">
        <el-checkbox v-for="c in channelOptions" :key="c.provider" :label="c.provider" style="display:block;margin:8px 0">
          {{ c.name }}（{{ c.provider }}）
        </el-checkbox>
      </el-checkbox-group>
      <el-empty v-if="!channelOptions.length" description="尚未配置或启用通知渠道，请先到「集成配置-通知渠道」添加" :image-size="60" />
      <template #footer>
        <el-button @click="notifyVisible = false">取消</el-button>
        <el-button type="primary" :loading="pushing" @click="doNotify">推送</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  ArrowLeft, Download, MagicStick, Monitor, Promotion, Tickets, TrendCharts, WarningFilled,
} from '@element-plus/icons-vue'
import api from '../../utils/api'
import EChart from '../../components/EChart.vue'
import { alertTag, analysisTag, fmtTime, severityTag } from '../../utils/format'
import { useThemeStore } from '../../stores/theme'

const route = useRoute()
const theme = useThemeStore()

const loading = ref(false)
const analyzing = ref(false)
const alert = reactive({})
const report = ref(null)
const notifications = ref([])
const channelOptions = ref([])
const metricCard = ref()

const visibleSeries = ref([])
const activeEvidence = ref(-1)
const notifyVisible = ref(false)
const notifyChannels = ref([])
const pushing = ref(false)
let pollTimer = null

const result = computed(() => report.value?.result || {})
const metricCtx = computed(() => report.value?.metric_context || {})
const series = computed(() => metricCtx.value.series || [])
const logs = computed(() =>
  (report.value?.log_context?.logs || []).map((l, i) => ({ ...l, _idx: i }))
)
const logPlatforms = computed(() => report.value?.log_context?.platforms || [])
const seriesStats = computed(() =>
  series.value.filter((s) => visibleSeries.value.includes(s.item_id))
)

const COLORS = ['#409eff', '#67c23a', '#e6a23c', '#f56c6c', '#9b59b6', '#1abc9c', '#e67e22', '#34495e', '#16a085', '#d35400']

const chartOption = computed(() => {
  const picked = seriesStats.value
  const alertTs = alert.occurred_at ? new Date(alert.occurred_at).getTime() : null
  const axisColor = theme.isDark ? '#c9d1d9' : '#606266'
  return {
    tooltip: { trigger: 'axis' },
    legend: { bottom: 0, type: 'scroll', textStyle: { color: axisColor } },
    grid: { left: 48, right: 18, top: 28, bottom: 56 },
    xAxis: {
      type: 'time',
      axisLabel: { color: axisColor, formatter: (v) => fmtTime(v).slice(11, 16) },
      axisLine: { lineStyle: { color: 'var(--el-border-color)' } },
    },
    yAxis: { type: 'value', axisLabel: { color: axisColor }, splitLine: { lineStyle: { color: 'var(--el-border-color-lighter)' } } },
    series: picked.map((s, idx) => ({
      name: s.name,
      type: 'line',
      smooth: true,
      showSymbol: false,
      sampling: 'lttb',
      itemStyle: { color: COLORS[idx % COLORS.length] },
      lineStyle: { width: 2 },
      areaStyle: { opacity: 0.06 },
      data: (s.points || []).map((p) => [p.ts * 1000, p.value]),
      markLine: idx === 0 && alertTs ? {
        symbol: 'none',
        lineStyle: { color: '#f56c6c', type: 'dashed', width: 2 },
        label: { formatter: '告警时刻', color: '#f56c6c', position: 'insideEndTop' },
        data: [{ xAxis: alertTs }],
      } : undefined,
    })),
  }
})

function changeColor(v) {
  if (v == null) return ''
  return v > 0 ? '#f56c6c' : '#67c23a'
}

function logLevelType(level) {
  const l = (level || '').toLowerCase()
  if (['error', 'err', 'fatal', 'crit', '严重', '错误'].some((x) => l.includes(x))) return 'danger'
  if (['warn', 'warning', '警告'].some((x) => l.includes(x))) return 'warning'
  return 'info'
}

function confidenceType(c) {
  const v = String(c || '').toLowerCase()
  if (v.includes('高') || v === 'high') return 'danger'
  if (v.includes('中') || v === 'medium') return 'warning'
  return 'info'
}

async function loadDetail() {
  loading.value = true
  try {
    const { data } = await api.get(`/alerts/${route.params.id}`)
    Object.assign(alert, data)
    report.value = data.report
    notifications.value = data.notifications
    visibleSeries.value = (data.report?.metric_context?.series || []).slice(0, 5).map((s) => s.item_id)
  } finally {
    loading.value = false
  }
}

async function loadChannels() {
  const { data } = await api.get('/configs', { params: { type: 'notify_channel' } })
  channelOptions.value = data.filter((c) => c.enabled)
}

async function runAnalyze() {
  analyzing.value = true
  try {
    // 后台异步执行：提交成功后进入轮询，直到 success/failed
    await api.post(`/alerts/${route.params.id}/analyze`)
    ElMessage.success('分析任务已提交，正在后台执行…')
    await loadDetail()
    startPolling()
  } catch (e) {
    if (e.response?.data?.code === 'analysis_busy') {
      ElMessage.info('分析进行中，页面将自动刷新结果')
      startPolling()
    } else if (e.response?.data?.message) {
      ElMessage.error(e.response.data.message)
    }
  } finally {
    analyzing.value = false
  }
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(async () => {
    try {
      await loadDetail()
      if (['success', 'failed'].includes(alert.analysis_status)) stopPolling()
    } catch (e) {
      // 单次轮询失败不致命；连续错误由定时器在下次继续，页面离开时 unmount 清理
    }
  }, 3000)
}
function stopPolling() {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = null
}

async function exportReport() {
  const resp = await api.get(`/reports/${report.value.id}/export`, { responseType: 'blob' })
  const url = URL.createObjectURL(resp.data)
  const a = document.createElement('a')
  a.href = url
  a.download = `itops-report-${alert.id}.md`
  a.click()
  URL.revokeObjectURL(url)
}

function openNotify() {
  notifyChannels.value = channelOptions.value.map((c) => c.provider)
  notifyVisible.value = true
}

async function doNotify() {
  if (!notifyChannels.value.length) {
    ElMessage.warning('请至少选择一个渠道')
    return
  }
  pushing.value = true
  try {
    await api.post(`/reports/${report.value.id}/notify`, { channels: notifyChannels.value })
    ElMessage.success('推送完成')
    notifyVisible.value = false
    await loadDetail()
  } finally {
    pushing.value = false
  }
}

// 证据链定位
function locate(ev) {
  const type = ev.type
  const ref = String(ev.ref || '')
  if (type === 'metric') {
    metricCard.value?.$el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    const target = series.value.find((s) => ref.includes(s.name) || s.name.includes(ref.replace(/^.*?\s/, '')))
    if (target && !visibleSeries.value.includes(target.item_id)) {
      visibleSeries.value = [...visibleSeries.value, target.item_id]
    }
    ElMessage.info('已定位到指标趋势图')
    return
  }
  // 日志：按时间片段或内容片段匹配
  const rows = document.querySelectorAll('.workbench .el-table__body tr')
  const key = ref.replace(/^L?\d*:?\s*/, '').trim()
  let idx = -1
  const list = logs.value
  for (let i = 0; i < list.length; i++) {
    const l = list[i]
    const hay = `${l.timestamp || fmtTime((l.ts || 0) * 1000)} ${l.message || ''}`
    if (key && hay.includes(key.slice(0, 12))) { idx = i; break }
  }
  if (idx >= 0 && rows[idx]) {
    activeEvidence.value = -1
    rows[idx].scrollIntoView({ behavior: 'smooth', block: 'center' })
    rows[idx].classList.add('log-row-flash')
    setTimeout(() => rows[idx].classList.remove('log-row-flash'), 1700)
    activeEvidence.value = result.value.evidence.indexOf(ev)
    ElMessage.success('已定位到关联日志')
  } else {
    ElMessage.info('该证据为模型引用的概括性信息，未匹配到单条日志')
  }
}

onMounted(async () => {
  await Promise.all([loadDetail(), loadChannels()])
  if (alert.analysis_status === 'processing') startPolling()
})
onBeforeUnmount(stopPolling)
</script>

<style scoped>
.panel {
  margin-bottom: 14px;
}
.alert-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.alert-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.alert-title {
  font-size: 17px;
  margin: 8px 0;
}
.alert-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 18px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.alert-meta .el-icon {
  vertical-align: -2px;
  margin-right: 2px;
}
.alert-head-actions {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  flex-shrink: 0;
}
.analysis-error {
  margin-top: 8px;
  color: var(--el-color-danger);
  font-size: 12px;
}
.series-chips {
  margin-bottom: 10px;
}
.cause-item {
  padding: 8px 0;
  border-bottom: 1px dashed var(--el-border-color-lighter);
}
.cause-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}
.cause-reason {
  margin-top: 4px;
  font-size: 12px;
  padding-left: 2px;
}
.evidence-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.evidence-line {
  font-size: 13px;
  padding: 6px 8px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
}
.evidence-line.active {
  border-color: var(--el-color-primary);
}
.evidence-ref {
  font-size: 12px;
}
.evidence-summary {
  margin-top: 2px;
}
.section-text {
  font-size: 13px;
  line-height: 1.7;
}
.step-list {
  margin: 0;
  padding-left: 20px;
  font-size: 13px;
  line-height: 1.9;
}
.notify-resp {
  font-size: 12px;
  word-break: break-all;
}
@media (max-width: 768px) {
  .alert-head-actions {
    width: 100%;
  }
  .alert-head-actions .el-button {
    flex: 1;
  }
}
</style>
