<template>
  <div class="page-container">
    <h2 class="page-title">已恢复告警</h2>

    <el-card shadow="never">
      <div class="toolbar">
        <el-input v-model="filters.host" placeholder="主机名关键字" clearable
                  style="width: 220px" @keyup.enter="reload()" :prefix-icon="Search" />
        <el-select v-model="filters.severities" placeholder="级别（可多选）" multiple collapse-tags
                   collapse-tags-tooltip clearable style="width: 200px" @change="reload()">
          <el-option v-for="s in severities" :key="s.value" :label="s.label" :value="s.value" />
        </el-select>
        <el-button type="primary" :icon="Search" @click="reload()">查询</el-button>
        <el-button :icon="Refresh" @click="reset">重置</el-button>
        <span class="flex-grow" />
        <el-button :icon="RefreshRight" :loading="loading" @click="reload()">刷新</el-button>
        <span class="text-muted" style="margin-left:8px;font-size:12px">
          共 {{ total }} 条
        </span>
      </div>

      <el-table :data="rows" v-loading="loading" stripe style="width: 100%">
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
        <el-table-column label="恢复时间" width="170">
          <template #default="{ row }">{{ fmtTime(row.recovered_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="$router.push(`/alerts/${row.event_id}`)">
              详情
            </el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无已恢复告警" />
        </template>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { Refresh, RefreshRight, Search } from '@element-plus/icons-vue'
import api from '../../utils/api'
import { fmtTime, severityTag } from '../../utils/format'

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

async function reload() {
  loading.value = true
  try {
    const params = { status: 'resolved', page_size: 200 }
    if (filters.host.trim()) params.host = filters.host.trim()
    if (filters.severities && filters.severities.length) {
      params.severities = filters.severities
    }
    const { data } = await api.get('/alerts', { params })
    rows.value = data.items || []
    total.value = data.total || 0
  } finally {
    loading.value = false
  }
}

function reset() {
  Object.assign(filters, { host: '', severities: [] })
  reload()
}

onMounted(reload)
</script>

<style scoped>
.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
}
</style>
