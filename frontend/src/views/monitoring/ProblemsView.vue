<template>
  <div class="page-container">
    <h2 class="page-title">Zabbix 当前未恢复问题</h2>

    <el-card shadow="never">
      <div class="filter-bar">
        <el-input v-model="hostKeyword" placeholder="主机名关键字" clearable
                  size="default" style="width:200px" @keyup.enter="loadProblems" />
        <el-select v-model="selectedSev" placeholder="告警级别" clearable
                   size="default" style="width:140px" @change="loadProblems">
          <el-option v-for="s in SEV_OPTIONS" :key="s.value"
                     :label="s.label" :value="s.value" />
        </el-select>
        <el-button type="primary" :icon="Search" @click="loadProblems">查询</el-button>
        <el-button :icon="Refresh" @click="resetFilter">重置</el-button>
      </div>

      <el-table :data="problems" v-loading="loading" size="small" style="margin-top:12px" stripe>
        <el-table-column label="主机" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-for="(h, i) in row.hosts" :key="i" class="host-tag">
              {{ h.name || h.host }}
            </span>
            <span v-if="!row.hosts?.length">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="问题描述" min-width="280" show-overflow-tooltip />
        <el-table-column label="级别" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="severityTag(sevLabel(row.severity))" size="small">
              {{ sevLabel(row.severity) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag type="warning" size="small" effect="plain">
              {{ row.acknowledged ? '已确认' : '未确认' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="发生时间" width="170" align="center">
          <template #default="{ row }">{{ fmtTime((row.clock || 0) * 1000) }}</template>
        </el-table-column>
        <template #empty><el-empty description="当前没有未恢复问题" :image-size="80" /></template>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { Refresh, Search } from '@element-plus/icons-vue'
import api from '../../utils/api'
import { fmtTime, severityTag } from '../../utils/format'

const SEV_MAP = { 0: '未分类', 1: '信息', 2: '警告', 3: '一般严重', 4: '严重', 5: '灾难' }
const SEV_OPTIONS = [
  { value: '0', label: '未分类' },
  { value: '1', label: '信息' },
  { value: '2', label: '警告' },
  { value: '3', label: '一般严重' },
  { value: '4', label: '严重' },
  { value: '5', label: '灾难' },
]
function sevLabel(v) {
  return SEV_MAP[String(v)] || (v ? String(v) : '未分级')
}

const hostKeyword = ref('')
const selectedSev = ref('')
const problems = ref([])
const loading = ref(false)

async function loadProblems() {
  loading.value = true
  try {
    const params = { limit: 100 }
    if (hostKeyword.value.trim()) params.host = hostKeyword.value.trim()
    if (selectedSev.value !== '' && selectedSev.value !== null) {
      params.severities = [selectedSev.value]
    }
    const { data } = await api.get('/zabbix/problems', { params })
    problems.value = data
  } finally {
    loading.value = false
  }
}

function resetFilter() {
  hostKeyword.value = ''
  selectedSev.value = ''
  loadProblems()
}

onMounted(loadProblems)
</script>

<style scoped>
.filter-bar {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}
.host-tag {
  display: inline-block;
  margin-right: 6px;
}
</style>
