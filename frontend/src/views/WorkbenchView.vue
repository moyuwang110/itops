<template>
  <div class="page-container workbench">
    <h2 class="page-title">工作台</h2>

    <!-- 统计卡片 -->
    <el-row :gutter="14">
      <el-col :xs="12" :sm="12" :md="6" v-for="c in statCards" :key="c.label">
        <el-card shadow="hover" class="stat-card" @click="c.action && c.action()">
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
      <!-- 待处理告警 -->
      <el-col :xs="24" :md="14">
        <el-card shadow="never">
          <template #header>
            <div class="card-header-flex">
              <span>当前未恢复告警</span>
              <div>
                <el-popconfirm v-if="wbSelectedIds.length"
                               :title="`确认忽略选中的 ${wbSelectedIds.length} 条？`"
                               @confirm="wbAcknowledgeBatch">
                  <template #reference>
                    <el-button link type="success" size="small" :loading="wbBatchLoading">
                      批量确认 ({{ wbSelectedIds.length }})
                    </el-button>
                  </template>
                </el-popconfirm>
                <el-link type="primary" @click="$router.push('/alerts')" style="margin-left:10px">全部告警</el-link>
              </div>
            </div>
          </template>
          <el-table :data="alerts" v-loading="loadingAlerts" size="small" stripe style="width: 100%"
                    @selection-change="onWbSelectionChange" ref="wbTableRef">
            <el-table-column type="selection" width="42" align="center" />
            <el-table-column label="主机" min-width="110" show-overflow-tooltip>
              <template #default="{ row }">
                <el-link type="primary" @click="$router.push(`/alerts/${row.event_id}`)">{{ row.host || '-' }}</el-link>
              </template>
            </el-table-column>
            <el-table-column prop="title" label="问题描述" min-width="160" show-overflow-tooltip />
            <el-table-column label="级别" width="86">
              <template #default="{ row }">
                <el-tag :type="severityTag(row.severity)" size="small">{{ row.severity || '-' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="170" align="center">
              <template #default="{ row }">
                <el-popconfirm title="确认忽略此告警？" @confirm="acknowledge(row)">
                  <template #reference>
                    <el-button link type="success" size="small" :loading="row._acknowledging">确认</el-button>
                  </template>
                </el-popconfirm>
                <el-button link type="primary" size="small" :loading="row._analyzing" @click="analyze(row)">分析</el-button>
              </template>
            </el-table-column>
            <template #empty><el-empty description="暂无未恢复告警" :image-size="70" /></template>
          </el-table>
        </el-card>
      </el-col>

      <!-- 最近报告 -->
      <el-col :xs="24" :md="10">
        <el-card shadow="never">
          <template #header>
            <div class="card-header-flex">
              <span>最近分析报告</span>
              <el-link type="primary" @click="$router.push('/reports')">全部报告</el-link>
            </div>
          </template>
          <el-table :data="reports" v-loading="loadingReports" size="small" stripe style="width: 100%">
            <el-table-column label="主机 / 告警" min-width="160" show-overflow-tooltip>
              <template #default="{ row }">
                <el-link type="primary" @click="$router.push(`/reports/${row.id}`)">
                  {{ row.alert?.host || '-' }}
                </el-link>
                <div class="text-muted" style="font-size:11px">{{ row.alert?.title }}</div>
              </template>
            </el-table-column>
            <el-table-column label="级别" width="76">
              <template #default="{ row }">
                <el-tag :type="severityTag(row.alert?.severity)" size="small">{{ row.alert?.severity || '-' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="生成时间" width="140">
              <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
            </el-table-column>
            <template #empty><el-empty description="暂无分析报告" :image-size="70" /></template>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <!-- 系统集成状态 -->
    <el-row :gutter="14" style="margin-top: 14px">
      <el-col :span="24">
        <el-card shadow="never">
          <template #header>
            <div class="card-header-flex">
              <span>集成配置状态</span>
              <el-link type="primary" @click="$router.push('/settings/zabbix')">管理配置</el-link>
            </div>
          </template>
          <el-table :data="integrations" size="small" stripe>
            <el-table-column label="类型" width="120">
              <template #default="{ row }">{{ row.type_label }}</template>
            </el-table-column>
            <el-table-column label="名称" min-width="160" show-overflow-tooltip>
              <template #default="{ row }">{{ row.name }}</template>
            </el-table-column>
            <el-table-column label="供应商" width="120">
              <template #default="{ row }"><span class="mono">{{ row.provider }}</span></template>
            </el-table-column>
            <el-table-column label="状态" width="100" align="center">
              <template #default="{ row }">
                <el-tag :type="row.enabled ? 'success' : 'info'" size="small">
                  {{ row.enabled ? '已启用' : '未启用' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="连通性" width="100" align="center">
              <template #default="{ row }">
                <el-tag v-if="row.last_test_ok" type="success" size="small" effect="plain">正常</el-tag>
                <el-tag v-else-if="row.last_test_at" type="danger" size="small" effect="plain">异常</el-tag>
                <span v-else class="text-muted">未检测</span>
              </template>
            </el-table-column>
            <el-table-column label="最近检测" min-width="160">
              <template #default="{ row }">
                <span v-if="row.last_test_at">{{ fmtTime(row.last_test_at) }}</span>
                <span v-else class="text-muted">-</span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import api from '../utils/api'
import { fmtTime, severityTag } from '../utils/format'

const router = useRouter()
const alerts = ref([])
const alertTotal = ref(0)
const reports = ref([])
const integrations = ref([])
const loadingAlerts = ref(false)
const loadingReports = ref(false)
// 工作台告警批量选择
const wbTableRef = ref(null)
const wbSelectedIds = ref([])
const wbBatchLoading = ref(false)

function onWbSelectionChange(selection) {
  wbSelectedIds.value = selection.map((r) => r.event_id)
}

const statCards = computed(() => [
  {
    label: '未恢复告警', value: alertTotal.value,
    icon: 'Bell', color: '#f56c6c', bg: 'rgba(245,108,108,.12)',
    action: () => router.push('/alerts'),
  },
  {
    label: '分析报告', value: reports.value.length,
    icon: 'Document', color: '#409eff', bg: 'rgba(64,158,255,.12)',
    action: () => router.push('/reports'),
  },
  {
    label: '已启用集成', value: integrations.value.filter((i) => i.enabled).length,
    icon: 'Connection', color: '#67c23a', bg: 'rgba(103,194,58,.12)',
    action: () => router.push('/settings/zabbix'),
  },
  {
    label: '连通正常', value: integrations.value.filter((i) => i.last_test_ok).length,
    icon: 'CircleCheck', color: '#e6a23c', bg: 'rgba(230,162,60,.12)',
  },
])

async function loadAlerts() {
  loadingAlerts.value = true
  try {
    const { data } = await api.get('/alerts', { params: { page_size: 10, sort: 'severity' } })
    alerts.value = (data.items || []).map((r) => ({ ...r, _analyzing: false, _acknowledging: false }))
    alertTotal.value = data.total || 0
    wbSelectedIds.value = []
    wbTableRef.value?.clearSelection()
  } finally {
    loadingAlerts.value = false
  }
}

async function loadReports() {
  loadingReports.value = true
  try {
    const { data } = await api.get('/reports', { params: { page: 1, page_size: 8 } })
    reports.value = data.items || []
  } finally {
    loadingReports.value = false
  }
}

async function loadIntegrations() {
  try {
    const { data } = await api.get('/dashboard/summary')
    integrations.value = data.integrations || []
  } catch {
    integrations.value = []
  }
}

async function analyze(row) {
  row._analyzing = true
  try {
    await api.post(`/alerts/${row.event_id}/analyze`)
    ElMessage.success('分析任务已提交，正在后台执行…')
    router.push(`/alerts/${row.event_id}`)
  } catch (e) {
    if (e.response?.data?.code === 'analysis_busy') {
      ElMessage.warning('该告警正在分析中，进入工作台查看')
      router.push(`/alerts/${row.event_id}`)
    } else if (e.response?.data?.message) {
      ElMessage.error(e.response.data.message)
    }
  } finally {
    row._analyzing = false
  }
}

async function acknowledge(row) {
  row._acknowledging = true
  try {
    await api.post(`/alerts/${row.event_id}/acknowledge`)
    ElMessage.success('已确认忽略该告警')
    alerts.value = alerts.value.filter((r) => r.event_id !== row.event_id)
    alertTotal.value = Math.max(0, alertTotal.value - 1)
  } catch (e) {
    if (e.response?.data?.message) {
      ElMessage.error(e.response.data.message)
    } else {
      ElMessage.error('确认失败，请重试')
    }
  } finally {
    row._acknowledging = false
  }
}

async function wbAcknowledgeBatch() {
  if (!wbSelectedIds.value.length) return
  wbBatchLoading.value = true
  try {
    const { data } = await api.post('/alerts/acknowledge-batch', { event_ids: wbSelectedIds.value })
    ElMessage.success(`已批量确认 ${data.acknowledged} 条告警`)
    const removed = new Set(wbSelectedIds.value)
    alerts.value = alerts.value.filter((r) => !removed.has(r.event_id))
    alertTotal.value = Math.max(0, alertTotal.value - data.acknowledged)
    wbSelectedIds.value = []
    wbTableRef.value?.clearSelection()
  } catch (e) {
    if (e.response?.data?.message) {
      ElMessage.error(e.response.data.message)
    } else {
      ElMessage.error('批量确认失败，请重试')
    }
  } finally {
    wbBatchLoading.value = false
  }
}

onMounted(() => {
  loadAlerts()
  loadReports()
  loadIntegrations()
})
</script>

<style scoped>
.stat-card {
  cursor: pointer;
  transition: transform 0.15s;
}
.stat-card:hover {
  transform: translateY(-2px);
}
.stat-card :deep(.el-card__body) {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px;
}
.stat-icon {
  width: 48px;
  height: 48px;
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
  margin-top: 2px;
}
.card-header-flex {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
}
</style>
