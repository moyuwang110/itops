<template>
  <div class="page-container">
    <h2 class="page-title">分析报告</h2>
    <el-card shadow="never">
      <div class="toolbar">
        <el-input v-model="keyword" placeholder="主机 / 告警标题" clearable style="width:240px"
                  :prefix-icon="Search" @keyup.enter="load(1)" />
        <el-select v-model="severity" placeholder="级别" clearable style="width:120px" @change="load(1)">
          <el-option v-for="s in severities" :key="s" :label="s" :value="s" />
        </el-select>
        <el-date-picker v-model="dateRange" type="datetimerange" range-separator="至"
                        start-placeholder="告警开始时间" end-placeholder="告警结束时间"
                        value-format="YYYY-MM-DDTHH:mm:ss" style="width:360px"
                        @change="load(1)" />
        <el-button type="primary" :icon="Search" @click="load(1)">查询</el-button>
      </div>

      <el-table :data="rows" v-loading="loading" stripe>
        <el-table-column label="报告ID" prop="id" width="80" />
        <el-table-column label="主机 / 告警" min-width="260">
          <template #default="{ row }">
            <div><b>{{ row.alert.host || '-' }}</b></div>
            <div class="text-muted" style="font-size:12px">{{ row.alert.title }}</div>
          </template>
        </el-table-column>
        <el-table-column label="级别" width="90">
          <template #default="{ row }">
            <el-tag :type="severityTag(row.alert.severity)" size="small">{{ row.alert.severity || '未分级' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="模型" width="150">
          <template #default="{ row }">
            <span class="mono" style="font-size:12px">{{ row.provider }}/{{ row.model }}</span>
            <el-tag v-if="row.degraded_from" size="small" type="warning" effect="plain" style="margin-left:4px">降级</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="耗时" width="90">
          <template #default="{ row }">{{ (row.duration_ms / 1000).toFixed(1) }}s</template>
        </el-table-column>
        <el-table-column label="生成时间" width="170">
          <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="190" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="$router.push(`/reports/${row.id}`)">查看</el-button>
            <el-button link type="primary" size="small" @click="goWorkbench(row)">工作台</el-button>
            <el-button link type="primary" size="small" @click="exportMd(row)">导出</el-button>
          </template>
        </el-table-column>
        <template #empty><el-empty description="暂无分析报告" /></template>
      </el-table>

      <div class="pager">
        <el-pagination background layout="total, prev, pager, next"
                       :total="total" :current-page="page" :page-size="pageSize"
                       @current-change="(p) => load(p)" />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Search } from '@element-plus/icons-vue'
import api from '../../utils/api'
import { fmtTime, severityTag } from '../../utils/format'

const router = useRouter()
const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const keyword = ref('')
const severity = ref('')
const dateRange = ref(null)
const loading = ref(false)
const severities = ['灾难', '严重', '一般严重', '警告', '信息', '未分类']

async function load(p) {
  if (p) page.value = p
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize }
    if (keyword.value) params.keyword = keyword.value
    if (severity.value) params.severity = severity.value
    if (dateRange.value && dateRange.value.length === 2) {
      params.start = dateRange.value[0]
      params.end = dateRange.value[1]
    }
    const { data } = await api.get('/reports', { params })
    rows.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

function goWorkbench(row) {
  router.push(`/alerts/${row.alert_id}`)
}

async function exportMd(row) {
  const resp = await api.get(`/reports/${row.id}/export`, { responseType: 'blob' })
  const url = URL.createObjectURL(resp.data)
  const a = document.createElement('a')
  a.href = url
  a.download = `itops-report-${row.alert_id}.md`
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(() => load(1))
</script>

<style scoped>
.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}
</style>
