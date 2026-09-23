<template>
  <div class="page-container">
    <h2 class="page-title">告警列表</h2>

    <el-card shadow="never">
      <div class="toolbar">
        <el-input v-model="filters.keyword" placeholder="主机 / 标题 / 事件ID" clearable
                  style="width: 220px" @keyup.enter="reload(1)" :prefix-icon="Search" />
        <el-select v-model="filters.status" placeholder="告警状态" clearable style="width: 130px" @change="reload(1)">
          <el-option label="未恢复" value="problem" />
          <el-option label="已恢复" value="resolved" />
        </el-select>
        <el-select v-model="filters.analysis_status" placeholder="分析状态" clearable style="width: 130px" @change="reload(1)">
          <el-option v-for="(v, k) in ANALYSIS_STATUS" :key="k" :label="v.label" :value="k" />
        </el-select>
        <el-select v-model="filters.severity" placeholder="级别" clearable style="width: 120px" @change="reload(1)">
          <el-option v-for="s in severities" :key="s" :label="s" :value="s" />
        </el-select>
        <el-button type="primary" :icon="Search" @click="reload(1)">查询</el-button>
        <el-button :icon="Refresh" @click="reset">重置</el-button>
        <span class="flex-grow" />
        <el-button :icon="RefreshRight" @click="reload()">刷新</el-button>
      </div>

      <el-table :data="rows" v-loading="loading" stripe style="width: 100%">
        <el-table-column label="主机" min-width="120" show-overflow-tooltip>
          <template #default="{ row }">
            <el-link type="primary" @click="$router.push(`/alerts/${row.id}`)">{{ row.host || '-' }}</el-link>
          </template>
        </el-table-column>
        <el-table-column prop="title" label="告警标题" min-width="220" show-overflow-tooltip />
        <el-table-column label="级别" width="92">
          <template #default="{ row }">
            <el-tag :type="severityTag(row.severity)" size="small">{{ row.severity || '未分级' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="86">
          <template #default="{ row }">
            <el-tag :type="alertTag(row.status).type" size="small">{{ alertTag(row.status).label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="分析状态" width="100">
          <template #default="{ row }">
            <el-tag :type="analysisTag(row.analysis_status).type" size="small" effect="plain">
              {{ analysisTag(row.analysis_status).label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="发生时间" width="170">
          <template #default="{ row }">{{ fmtTime(row.occurred_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small"
                       :loading="row._analyzing"
                       @click="analyze(row)">
              {{ row.analysis_status === 'pending' ? '分析' : '重新分析' }}
            </el-button>
            <el-button link type="primary" size="small" @click="$router.push(`/alerts/${row.id}`)">
              工作台
            </el-button>
          </template>
        </el-table-column>
        <template #empty><el-empty description="暂无告警" /></template>
      </el-table>

      <div class="pager">
        <el-pagination background layout="total, prev, pager, next, sizes"
                       :total="total" :current-page="filters.page" :page-size="filters.page_size"
                       :page-sizes="[20, 50, 100]"
                       @current-change="(p) => reload(p)"
                       @size-change="onSize" />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, RefreshRight, Search } from '@element-plus/icons-vue'
import api from '../../utils/api'
import { ANALYSIS_STATUS, alertTag, analysisTag, fmtTime, severityTag } from '../../utils/format'

const severities = ['灾难', '严重', '一般严重', '警告', '信息', '未分类']
const rows = ref([])
const total = ref(0)
const loading = ref(false)
const filters = reactive({ keyword: '', status: '', analysis_status: '', severity: '', page: 1, page_size: 20 })

async function reload(page) {
  if (page) filters.page = page
  loading.value = true
  try {
    const params = { page: filters.page, page_size: filters.page_size }
    for (const k of ['keyword', 'status', 'analysis_status', 'severity']) {
      if (filters[k]) params[k] = filters[k]
    }
    const { data } = await api.get('/alerts', { params })
    rows.value = data.items.map((r) => ({ ...r, _analyzing: false }))
    total.value = data.total
  } finally {
    loading.value = false
  }
}

function reset() {
  Object.assign(filters, { keyword: '', status: '', analysis_status: '', severity: '', page: 1 })
  reload(1)
}

function onSize(size) {
  filters.page_size = size
  reload(1)
}

async function analyze(row) {
  row._analyzing = true
  try {
    // 后台异步执行：提交后延迟刷新列表状态，最终结果在工作台轮询查看
    await api.post(`/alerts/${row.id}/analyze`)
    ElMessage.success('分析任务已提交，后台执行中…可进入工作台查看进度')
    setTimeout(() => reload(), 2500)
  } catch (e) {
    if (e.response?.data?.code === 'analysis_busy') {
      ElMessage.warning('该告警正在分析中，请稍后进入工作台查看')
    } else if (e.response?.data?.message) {
      ElMessage.error(e.response.data.message)
    }
  } finally {
    row._analyzing = false
  }
}

onMounted(() => reload(1))
</script>

<style scoped>
.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}
</style>
