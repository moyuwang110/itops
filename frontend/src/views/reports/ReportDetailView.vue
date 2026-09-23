<template>
  <div class="page-container" v-loading="loading">
    <div class="head-row">
      <el-button :icon="ArrowLeft" link @click="$router.push('/reports')">返回报告列表</el-button>
      <div>
        <el-button :icon="Promotion" @click="goWorkbench">进入告警工作台</el-button>
        <el-button type="primary" :icon="Download" @click="exportMd">导出 Markdown</el-button>
      </div>
    </div>

    <el-card v-if="report" shadow="never" style="margin-top:10px">
      <template #header>
        <div class="report-head">
          <div>
            <el-tag :type="severityTag(report.alert?.severity)" size="small">{{ report.alert?.severity || '未分级' }}</el-tag>
            <b style="margin-left:8px">{{ report.alert?.title }}</b>
            <span class="text-muted" style="margin-left:8px">{{ report.alert?.host }}</span>
          </div>
          <div class="text-muted">
            <span class="mono">{{ report.provider }}/{{ report.model }}</span>
            · {{ fmtTime(report.created_at) }} · 耗时 {{ (report.duration_ms / 1000).toFixed(1) }}s
          </div>
        </div>
      </template>

      <el-tabs v-model="tab">
        <el-tab-pane label="结构化结论" name="structured">
          <h4>可能根因</h4>
          <el-table :data="result.root_causes || []" size="small" border>
            <el-table-column label="置信度" width="100">
              <template #default="{ row }">
                <el-tag size="small" effect="plain">{{ typeof row === 'string' ? '-' : row.confidence }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="根因" min-width="200">
              <template #default="{ row }">{{ typeof row === 'string' ? row : row.cause }}</template>
            </el-table-column>
            <el-table-column label="依据" min-width="240">
              <template #default="{ row }">{{ typeof row === 'string' ? '' : row.reason }}</template>
            </el-table-column>
            <template #empty>无</template>
          </el-table>

          <h4>证据链</h4>
          <el-table :data="result.evidence || []" size="small" border>
            <el-table-column prop="type" label="类型" width="90" />
            <el-table-column prop="ref" label="引用" width="180" show-overflow-tooltip />
            <el-table-column prop="summary" label="说明" min-width="240" show-overflow-tooltip />
            <template #empty>无</template>
          </el-table>

          <h4>影响范围</h4>
          <div class="block-text">{{ result.impact || '未评估' }}</div>

          <h4>处置建议</h4>
          <ol v-if="result.remediation?.length" class="steps">
            <li v-for="(s, i) in result.remediation" :key="i">{{ typeof s === 'string' ? s : s.step }}</li>
          </ol>
          <div v-else class="text-muted">无</div>

          <h4>预防建议</h4>
          <ol v-if="result.prevention?.length" class="steps">
            <li v-for="(s, i) in result.prevention" :key="i">{{ typeof s === 'string' ? s : s.step }}</li>
          </ol>
          <div v-else class="text-muted">无</div>
        </el-tab-pane>

        <el-tab-pane label="Markdown 原文" name="md">
          <pre class="md-pre">{{ report.markdown }}</pre>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Download, Promotion } from '@element-plus/icons-vue'
import api from '../../utils/api'
import { fmtTime, severityTag } from '../../utils/format'

const route = useRoute()
const router = useRouter()
const report = ref(null)
const loading = ref(false)
const tab = ref('structured')
const result = ref({})

async function load() {
  loading.value = true
  try {
    const { data } = await api.get(`/reports/${route.params.id}`)
    report.value = data
    result.value = data.result || {}
  } finally {
    loading.value = false
  }
}

function goWorkbench() {
  router.push(`/alerts/${report.value.alert_id}`)
}

async function exportMd() {
  const resp = await api.get(`/reports/${route.params.id}/export`, { responseType: 'blob' })
  const url = URL.createObjectURL(resp.data)
  const a = document.createElement('a')
  a.href = url
  a.download = `itops-report-${report.value.alert_id}.md`
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(load)
</script>

<style scoped>
.head-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.report-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}
h4 {
  margin: 16px 0 8px;
}
.block-text {
  background: var(--el-fill-color-light);
  border-radius: 6px;
  padding: 10px 12px;
  font-size: 13px;
  line-height: 1.8;
  white-space: pre-wrap;
}
.steps {
  font-size: 13px;
  line-height: 2;
  margin: 0;
  padding-left: 22px;
}
.md-pre {
  background: var(--el-fill-color-light);
  border-radius: 6px;
  padding: 14px;
  font-size: 12px;
  line-height: 1.7;
  overflow: auto;
  max-height: 70vh;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
