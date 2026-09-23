<template>
  <div class="page-container">
    <h2 class="page-title">监控数据（Zabbix）</h2>

    <el-row :gutter="14">
      <el-col :xs="24" :md="8" :lg="6">
        <el-card shadow="never" class="full-height">
          <template #header>
            <div class="card-head">
              <span>主机</span>
              <el-button link type="primary" :icon="Search" @click="loadHosts">搜索</el-button>
            </div>
          </template>
          <el-input v-model="hostKeyword" placeholder="主机名关键字" clearable size="small"
                    @keyup.enter="loadHosts" style="margin-bottom:10px" />
          <el-table :data="hosts" v-loading="hostLoading" size="small" highlight-current-row
                    @current-change="onHost" height="560">
            <el-table-column prop="host" label="主机名" min-width="110" show-overflow-tooltip />
            <el-table-column prop="ip" label="IP" width="110" show-overflow-tooltip />
            <template #empty><el-empty description="输入关键字搜索主机" :image-size="60" /></template>
          </el-table>
        </el-card>
      </el-col>

      <el-col :xs="24" :md="16" :lg="18">
        <el-card shadow="never">
          <template #header>
            <div class="card-head">
              <span>监控项 / 历史趋势</span>
              <el-radio-group v-if="selectedItem" v-model="rangeMin" size="small" @change="loadHistory">
                <el-radio-button :value="30">30分钟</el-radio-button>
                <el-radio-button :value="60">1小时</el-radio-button>
                <el-radio-button :value="360">6小时</el-radio-button>
                <el-radio-button :value="1440">24小时</el-radio-button>
              </el-radio-group>
            </div>
          </template>

          <div v-if="currentHost">
            <el-input v-model="itemKeyword" placeholder="过滤监控项（如 cpu / memory）" clearable
                      size="small" style="margin-bottom:10px;max-width:280px" />
            <el-table :data="filteredItems" v-loading="itemLoading" size="small" height="210"
                      highlight-current-row @current-change="onItem">
              <el-table-column prop="name" label="监控项" min-width="180" show-overflow-tooltip />
              <el-table-column prop="key_" label="Key" min-width="150" show-overflow-tooltip />
              <el-table-column label="末值" width="110">
                <template #default="{ row }">
                  <span class="mono">{{ row.last_value }}{{ row.units }}</span>
                </template>
              </el-table-column>
              <template #empty><el-empty description="该主机暂无监控项" :image-size="50" /></template>
            </el-table>

            <el-skeleton v-if="histLoading" :rows="5" animated style="margin-top:14px" />
            <div v-else-if="selectedItem" style="margin-top:14px">
              <div class="item-summary">
                <b>{{ selectedItem.name }}</b>
                <el-tag size="small" effect="plain" style="margin-left:8px">
                  value_type={{ selectedItem.value_type }}
                </el-tag>
              </div>
              <EChart v-if="points.length" :option="histOption" height="320px" />
              <el-empty v-else description="所选窗口内没有历史数据" :image-size="70" />
            </div>
            <el-empty v-else description="选择左侧主机与上方监控项查看趋势" :image-size="70" />
          </div>
          <el-empty v-else description="请先选择一台主机" :image-size="90" />
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" style="margin-top:14px">
      <template #header>
        <div class="card-head">
          <span>Zabbix 当前未恢复问题</span>
          <el-button link type="primary" @click="loadProblems">刷新</el-button>
        </div>
      </template>
      <el-table :data="problems" v-loading="problemLoading" size="small">
        <el-table-column label="主机" min-width="120" show-overflow-tooltip>
          <template #default="{ row }">{{ row.hosts?.[0]?.host || '-' }}</template>
        </el-table-column>
        <el-table-column prop="name" label="问题" min-width="240" show-overflow-tooltip />
        <el-table-column label="级别" width="90">
          <template #default="{ row }">
            <el-tag :type="severityTag(sevLabel(row.severity))" size="small">{{ sevLabel(row.severity) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="发生时间" width="170">
          <template #default="{ row }">{{ fmtTime((row.clock || 0) * 1000) }}</template>
        </el-table-column>
        <template #empty><el-empty description="当前没有未恢复问题" :image-size="60" /></template>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Search } from '@element-plus/icons-vue'
import api from '../../utils/api'
import EChart from '../../components/EChart.vue'
import { fmtTime, severityTag } from '../../utils/format'
import { useThemeStore } from '../../stores/theme'

const SEV_MAP = { 0: '未分类', 1: '信息', 2: '警告', 3: '一般严重', 4: '严重', 5: '灾难' }
function sevLabel(v) {
  return SEV_MAP[String(v)] || (v ? String(v) : '未分级')
}

const theme = useThemeStore()
const hostKeyword = ref('')
const hosts = ref([])
const hostLoading = ref(false)
const currentHost = ref(null)
const itemKeyword = ref('')
const items = ref([])
const itemLoading = ref(false)
const selectedItem = ref(null)
const rangeMin = ref(60)
const points = ref([])
const histLoading = ref(false)
const problems = ref([])
const problemLoading = ref(false)

const filteredItems = computed(() => {
  const k = itemKeyword.value.trim().toLowerCase()
  if (!k) return items.value
  return items.value.filter((i) => `${i.name}${i.key_}`.toLowerCase().includes(k))
})

async function loadHosts() {
  hostLoading.value = true
  try {
    const { data } = await api.get('/zabbix/hosts', { params: { keyword: hostKeyword.value } })
    hosts.value = data
  } finally {
    hostLoading.value = false
  }
}

async function onHost(row) {
  if (!row) return
  currentHost.value = row
  items.value = []
  selectedItem.value = null
  points.value = []
  itemLoading.value = true
  try {
    const { data } = await api.get('/zabbix/items', { params: { host_id: row.host_id, limit: 500 } })
    items.value = data
  } finally {
    itemLoading.value = false
  }
}

async function onItem(row) {
  if (!row) return
  selectedItem.value = row
  await loadHistory()
}

async function loadHistory() {
  if (!selectedItem.value) return
  histLoading.value = true
  try {
    const now = Math.floor(Date.now() / 1000)
    const { data } = await api.get('/zabbix/history', {
      params: {
        item_id: selectedItem.value.item_id,
        value_type: selectedItem.value.value_type ?? 0,
        start: now - rangeMin.value * 60,
        end: now,
        limit: 2000,
      },
    })
    points.value = data.points
  } finally {
    histLoading.value = false
  }
}

const histOption = computed(() => {
  const axisColor = theme.isDark ? '#c9d1d9' : '#606266'
  const s = selectedItem.value
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 56, right: 20, top: 24, bottom: 40 },
    xAxis: {
      type: 'time',
      axisLabel: { color: axisColor, formatter: (v) => new Date(v).toLocaleTimeString('zh-CN', { hour12: false }) },
    },
    yAxis: {
      type: 'value',
      name: s?.units || '',
      axisLabel: { color: axisColor },
      splitLine: { lineStyle: { color: 'var(--el-border-color-lighter)' } },
    },
    series: [{
      type: 'line',
      smooth: true,
      showSymbol: false,
      sampling: 'lttb',
      itemStyle: { color: '#409eff' },
      areaStyle: { opacity: 0.08 },
      data: points.value.map((p) => [p.ts * 1000, p.value]),
    }],
  }
})

async function loadProblems() {
  problemLoading.value = true
  try {
    const { data } = await api.get('/zabbix/problems', { params: { limit: 50 } })
    problems.value = data
  } finally {
    problemLoading.value = false
  }
}

onMounted(() => {
  loadHosts()
  loadProblems()
})
</script>

<style scoped>
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.item-summary {
  margin-bottom: 8px;
  font-size: 13px;
}
.full-height :deep(.el-card__body) {
  padding-bottom: 12px;
}
</style>
