<template>
  <div class="page-container">
    <h2 class="page-title">告警列表</h2>

    <el-card shadow="never">
      <div class="toolbar">
        <el-input v-model="filters.host" placeholder="主机名关键字" clearable
                  style="width: 220px" @keyup.enter="reload(1)" :prefix-icon="Search" />
        <el-select v-model="filters.severities" placeholder="级别（可多选）" multiple collapse-tags
                   collapse-tags-tooltip clearable style="width: 200px" @change="reload()">
          <el-option v-for="s in severities" :key="s.value" :label="s.label" :value="s.value" />
        </el-select>
        <el-button type="primary" :icon="Search" @click="reload(1)">查询</el-button>
        <el-button :icon="Refresh" @click="reset">重置</el-button>
        <span class="flex-grow" />
        <el-button :icon="RefreshRight" :loading="loading" @click="reload()">刷新</el-button>
        <span class="text-muted" style="margin-left:8px;font-size:12px">
          每 60 秒从 Zabbix 同步 · 共 {{ total }} 条
        </span>
        <el-popconfirm v-if="selectedIds.length"
                       :title="`确认忽略选中的 ${selectedIds.length} 条告警？`"
                       @confirm="acknowledgeBatch">
          <template #reference>
            <el-button type="success" :icon="Check" :loading="batchLoading">
              批量确认 ({{ selectedIds.length }})
            </el-button>
          </template>
        </el-popconfirm>
      </div>

      <el-table :data="rows" v-loading="loading" stripe style="width: 100%"
                @selection-change="onSelectionChange" ref="tableRef">
        <el-table-column type="selection" width="48" align="center" />
        <el-table-column label="主机" min-width="120" show-overflow-tooltip>
          <template #default="{ row }">
            <el-link type="primary" @click="$router.push(`/alerts/${row.event_id}`)">
              {{ row.host || '-' }}
            </el-link>
          </template>
        </el-table-column>
        <el-table-column prop="title" label="问题描述" min-width="260" show-overflow-tooltip />
        <el-table-column label="级别" width="92">
          <template #default="{ row }">
            <el-tag :type="severityTag(row.severity)" size="small">{{ row.severity || '未分级' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="事件 ID" width="140" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="mono">{{ row.event_id }}</span>
          </template>
        </el-table-column>
        <el-table-column label="发生时间" width="170">
          <template #default="{ row }">{{ fmtTime(row.occurred_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="240" fixed="right">
          <template #default="{ row }">
            <el-popconfirm title="确认忽略此告警？确认后将从告警列表隐藏。"
                           @confirm="acknowledge(row)">
              <template #reference>
                <el-button link type="success" size="small" :loading="row._acknowledging">
                  确认
                </el-button>
              </template>
            </el-popconfirm>
            <el-button link type="primary" size="small"
                       :loading="row._analyzing"
                       @click="analyze(row)">
              分析
            </el-button>
            <el-button link type="primary" size="small" @click="$router.push(`/alerts/${row.event_id}`)">
              工作台
            </el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无未恢复问题（Zabbix 当前无 active problem）" />
        </template>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Check, Refresh, RefreshRight, Search } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import api from '../../utils/api'
import { fmtTime, severityTag } from '../../utils/format'

const router = useRouter()

// Zabbix 级别（数字）→ 中文标签，与后端 _SEVERITY_NUM_TO_LABEL 一致
const severities = [
  { value: 5, label: '灾难' },
  { value: 4, label: '严重' },
  { value: 3, label: '一般严重' },
  { value: 2, label: '警告' },
  { value: 1, label: '信息' },
  { value: 0, label: '未分类' },
]
const rows = ref([])
const total = ref(0)
const loading = ref(false)
const filters = reactive({ host: '', severities: [] })
// 批量选择
const tableRef = ref(null)
const selectedIds = ref([])
const batchLoading = ref(false)

function onSelectionChange(selection) {
  selectedIds.value = selection.map((r) => r.event_id)
}

async function reload() {
  loading.value = true
  try {
    const params = { page_size: 200 }
    if (filters.host.trim()) params.host = filters.host.trim()
    if (filters.severities && filters.severities.length) {
      params.severities = filters.severities
    }
    const { data } = await api.get('/alerts', { params })
    rows.value = data.items.map((r) => ({ ...r, _analyzing: false, _acknowledging: false }))
    total.value = data.total
    // 数据刷新后清空选中态
    selectedIds.value = []
    tableRef.value?.clearSelection()
  } finally {
    loading.value = false
  }
}

function reset() {
  Object.assign(filters, { host: '', severities: [] })
  reload()
}

async function analyze(row) {
  row._analyzing = true
  try {
    // 提交后跳转到工作台，由工作台轮询查看进度
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
    // 从列表中移除该行
    rows.value = rows.value.filter((r) => r.event_id !== row.event_id)
    total.value = rows.value.length
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

async function acknowledgeBatch() {
  if (!selectedIds.value.length) return
  batchLoading.value = true
  try {
    const { data } = await api.post('/alerts/acknowledge-batch', { event_ids: selectedIds.value })
    const successCount = data.acknowledged
    ElMessage.success(`已批量确认 ${successCount} 条告警`)
    // 从列表中移除已确认的行
    const removed = new Set(selectedIds.value)
    rows.value = rows.value.filter((r) => !removed.has(r.event_id))
    total.value = rows.value.length
    selectedIds.value = []
    tableRef.value?.clearSelection()
  } catch (e) {
    if (e.response?.data?.message) {
      ElMessage.error(e.response.data.message)
    } else {
      ElMessage.error('批量确认失败，请重试')
    }
  } finally {
    batchLoading.value = false
  }
}

onMounted(reload)
</script>

<style scoped>
.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
}
</style>
