<template>
  <div class="page-container">
    <h2 class="page-title">总览仪表盘</h2>

    <el-row :gutter="14">
      <el-col :xs="12" :sm="12" :md="6" v-for="c in statCards" :key="c.label">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-icon" :style="{ background: c.bg, color: c.color }">
            <el-icon :size="22"><component :is="c.icon" /></el-icon>
          </div>
          <div class="stat-body">
            <div class="stat-value">{{ c.value }}</div>
            <div class="stat-label">{{ c.label }}</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="14" style="margin-top: 14px">
      <el-col :xs="24" :md="12">
        <el-card shadow="never">
          <template #header>24 小时告警级别分布</template>
          <EChart v-if="hasSeverity" :option="severityOption" height="280px" />
          <el-empty v-else description="近 24 小时无告警" :image-size="80" />
        </el-card>
      </el-col>
      <el-col :xs="24" :md="12">
        <el-card shadow="never">
          <template #header>告警恢复状态</template>
          <EChart v-if="total24h > 0" :option="statusOption" height="280px" />
          <el-empty v-else description="近 24 小时无告警" :image-size="80" />
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="14" style="margin-top: 14px">
      <el-col :xs="24" :md="14">
        <el-card shadow="never">
          <template #header>
            <div class="card-header-flex">
              <span>最新告警</span>
              <el-link type="primary" @click="$router.push('/alerts')">全部告警</el-link>
            </div>
          </template>
          <el-table :data="summary.latest_alerts" size="small" stripe style="width: 100%">
            <el-table-column prop="host" label="主机" min-width="110" show-overflow-tooltip />
            <el-table-column prop="title" label="告警" min-width="160" show-overflow-tooltip />
            <el-table-column label="级别" width="86">
              <template #default="{ row }">
                <el-tag :type="severityTag(row.severity)" size="small">{{ row.severity || '-' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="80">
              <template #default="{ row }">
                <el-tag :type="alertTag(row.status).type" size="small">{{ alertTag(row.status).label }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="分析" width="86">
              <template #default="{ row }">
                <el-tag :type="analysisTag(row.analysis_status).type" size="small" effect="plain">
                  {{ analysisTag(row.analysis_status).label }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="70" fixed="right">
              <template #default="{ row }">
                <el-link type="primary" @click="$router.push(`/alerts/${row.id}`)">工作台</el-link>
              </template>
            </el-table-column>
            <template #empty><el-empty description="暂无告警" :image-size="60" /></template>
          </el-table>
        </el-card>
      </el-col>
      <el-col :xs="24" :md="10">
        <el-card shadow="never">
          <template #header>集成运行状态</template>
          <div v-for="g in groupedIntegrations" :key="g.type" class="integration-group">
            <div class="group-title">{{ g.label }}</div>
            <div v-for="i in g.items" :key="i.type + i.provider + i.name" class="integration-item">
              <div>
                <span class="integration-name">{{ i.name }}</span>
                <el-tag v-if="i.is_default" size="small" type="success" effect="plain" style="margin-left:6px">默认</el-tag>
                <span class="text-muted mono" style="margin-left:6px">{{ i.provider }}</span>
              </div>
              <div class="integration-right">
                <el-tag v-if="!i.enabled" size="small" type="info" effect="plain">已停用</el-tag>
                <el-tag v-else-if="i.last_test_ok === true" size="small" type="success">测试正常</el-tag>
                <el-tag v-else-if="i.last_test_ok === false" size="small" type="danger">测试失败</el-tag>
                <el-tag v-else size="small" type="warning" effect="plain">未测试</el-tag>
              </div>
            </div>
            <el-empty v-if="!g.items.length" :description="`未配置${g.label}`" :image-size="40" />
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive } from 'vue'
import api from '../utils/api'
import EChart from '../components/EChart.vue'
import { alertTag, analysisTag, severityTag } from '../utils/format'
import { useThemeStore } from '../stores/theme'

const theme = useThemeStore()
const summary = reactive({
  total_24h: 0,
  severity_dist: {},
  status_dist: { problem: 0, resolved: 0 },
  analysis: { success: 0, failed: 0, processing: 0, pending: 0, success_rate: null },
  latest_alerts: [],
  integrations: [],
})

const total24h = computed(() => summary.total_24h)
const hasSeverity = computed(() => Object.keys(summary.severity_dist).length > 0)

const statCards = computed(() => [
  { label: '24 小时告警', value: summary.total_24h, icon: 'Bell', color: '#409eff', bg: 'rgba(64,158,255,.12)' },
  { label: '分析成功率', value: summary.analysis.success_rate == null ? '-' : `${summary.analysis.success_rate}%`, icon: 'CircleCheck', color: '#67c23a', bg: 'rgba(103,194,58,.12)' },
  { label: '待处理告警', value: summary.status_dist.problem || 0, icon: 'Warning', color: '#f56c6c', bg: 'rgba(245,108,108,.12)' },
  { label: '启用集成', value: enabledCount.value, icon: 'Connection', color: '#e6a23c', bg: 'rgba(230,162,60,.12)' },
])

const enabledCount = computed(() => summary.integrations.filter((i) => i.enabled).length)

const groupedIntegrations = computed(() => {
  const labels = { zabbix: 'Zabbix', llm: '大模型', log_platform: '日志平台', notify_channel: '通知渠道' }
  return Object.keys(labels).map((type) => ({
    type,
    label: labels[type],
    items: summary.integrations.filter((i) => i.type === type),
  }))
})

const severityOption = computed(() => {
  const entries = Object.entries(summary.severity_dist)
  const palette = { 灾难: '#f56c6c', 严重: '#f56c6c', 一般严重: '#e6a23c', 警告: '#e6a23c', 信息: '#909399', 未分类: '#c0c4cc' }
  return {
    tooltip: { trigger: 'item' },
    legend: { bottom: 0, textStyle: { color: theme.isDark ? '#c9d1d9' : '#606266' } },
    series: [{
      type: 'pie',
      radius: ['42%', '68%'],
      center: ['50%', '44%'],
      label: { formatter: '{b}: {c}' },
      data: entries.map(([name, value]) => ({ name, value, itemStyle: { color: palette[name] || '#409eff' } })),
    }],
  }
})

const statusOption = computed(() => ({
  tooltip: { trigger: 'item' },
  legend: { bottom: 0, textStyle: { color: theme.isDark ? '#c9d1d9' : '#606266' } },
  series: [{
    type: 'pie',
    radius: ['55%', '72%'],
    center: ['50%', '44%'],
    label: { position: 'center', fontSize: 18, formatter: `${summary.total_24h}\n总告警` },
    data: [
      { name: '未恢复', value: summary.status_dist.problem || 0, itemStyle: { color: '#f56c6c' } },
      { name: '已恢复', value: summary.status_dist.resolved || 0, itemStyle: { color: '#67c23a' } },
    ],
  }],
}))

async function load() {
  const { data } = await api.get('/dashboard/summary')
  Object.assign(summary, data)
}

onMounted(load)
</script>

<style scoped>
.stat-card :deep(.el-card__body) {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 18px;
}
.stat-icon {
  width: 46px;
  height: 46px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.stat-value {
  font-size: 24px;
  font-weight: 700;
  line-height: 1.2;
}
.stat-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.card-header-flex {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.integration-group {
  margin-bottom: 12px;
}
.group-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  margin-bottom: 6px;
}
.integration-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 7px 4px;
  border-bottom: 1px dashed var(--el-border-color-lighter);
}
.integration-name {
  font-size: 13px;
  font-weight: 500;
}
@media (max-width: 768px) {
  .stat-card :deep(.el-card__body) { padding: 12px; }
  .stat-value { font-size: 20px; }
}
</style>
