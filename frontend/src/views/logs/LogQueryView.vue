<template>
  <div class="page-container">
    <h2 class="page-title">日志查询</h2>

    <el-card shadow="never">
      <div class="toolbar">
        <el-select v-model="platform" placeholder="选择日志平台" style="width:180px">
          <el-option v-for="p in platforms" :key="p.provider"
                     :label="`${p.name}（${p.provider}）`" :value="p.provider" />
        </el-select>
        <el-input v-model="keyword" placeholder="关键词（多词以空格分隔，OR 语义）" clearable
                  style="width:300px" @keyup.enter="query" />
        <el-input v-model="host" placeholder="主机名（可选）" clearable style="width:180px" @keyup.enter="query" />
        <el-date-picker v-model="range" type="datetimerange" range-separator="至"
                        start-placeholder="开始" end-placeholder="结束"
                        :shortcuts="shortcuts" style="width:360px" />
        <el-button type="primary" :icon="Search" :loading="loading" @click="query">查询</el-button>
      </div>

      <el-table :data="logs" v-loading="loading" size="small" stripe height="560">
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ row.timestamp || fmtTime((row.ts || 0) * 1000) }}</template>
        </el-table-column>
        <el-table-column label="平台" width="96">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ row.platform || platform }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="级别" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="levelType(row.level)" effect="plain">{{ row.level || '-' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="host" label="主机" width="120" show-overflow-tooltip />
        <el-table-column prop="source" label="来源" width="130" show-overflow-tooltip />
        <el-table-column prop="message" label="日志内容" min-width="320" show-overflow-tooltip />
        <template #empty>
          <el-empty v-if="!platforms.length" description="尚未配置或启用日志平台，请先到「集成配置-日志平台」添加" />
          <el-empty v-else description="选择平台与时间范围后查询" />
        </template>
      </el-table>
      <div class="text-muted" v-if="logs.length" style="margin-top:8px">共 {{ logs.length }} 条（最多展示 500 条）</div>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { Search } from '@element-plus/icons-vue'
import api from '../../utils/api'
import { fmtTime } from '../../utils/format'

const platforms = ref([])
const platform = ref('')
const keyword = ref('')
const host = ref('')
const range = ref(defaultRange())
const logs = ref([])
const loading = ref(false)

function defaultRange() {
  const end = new Date()
  const start = new Date(end.getTime() - 30 * 60 * 1000)
  return [start, end]
}

const shortcuts = [
  { text: '最近15分钟', value: () => { const e = new Date(); return [new Date(e - 15 * 60000), e] } },
  { text: '最近1小时', value: () => { const e = new Date(); return [new Date(e - 3600000), e] } },
  { text: '最近6小时', value: () => { const e = new Date(); return [new Date(e - 6 * 3600000), e] } },
  { text: '最近24小时', value: () => { const e = new Date(); return [new Date(e - 24 * 3600000), e] } },
]

function levelType(level) {
  const l = (level || '').toLowerCase()
  if (['error', 'err', 'fatal', 'crit'].some((x) => l.includes(x))) return 'danger'
  if (['warn', 'warning'].some((x) => l.includes(x))) return 'warning'
  return 'info'
}

async function loadPlatforms() {
  const { data } = await api.get('/logs/platforms')
  platforms.value = data
  if (data.length) platform.value = data[0].provider
}

async function query() {
  if (!platform.value) return
  loading.value = true
  try {
    const { data } = await api.get('/logs/query', {
      params: {
        platform: platform.value,
        keyword: keyword.value,
        host: host.value,
        start: range.value?.[0]?.toISOString(),
        end: range.value?.[1]?.toISOString(),
        limit: 500,
      },
    })
    logs.value = data.logs || []
  } finally {
    loading.value = false
  }
}

onMounted(loadPlatforms)
</script>
