<template>
  <div class="page-container">
    <div class="page-head">
      <h2 class="page-title">CMDB 配置项</h2>
      <div class="filters">
        <el-select v-model="filter.ci_type" placeholder="CI 类型" clearable style="width: 180px"
                   @change="onCiTypeChange">
          <el-option v-for="t in ciTypes" :key="t.value" :label="t.label" :value="t.value" />
        </el-select>
        <el-input v-model="filter.keyword" placeholder="搜索名称/IP/关键字" clearable style="width: 260px"
                  @keyup.enter="loadCis" @clear="loadCis">
          <template #append>
            <el-button :icon="Search" @click="loadCis" />
          </template>
        </el-input>
        <el-button @click="loadAll">刷新</el-button>
        <el-button type="primary" plain @click="openCmdb" v-if="cmdbUrl">
          打开 CMDB 系统
        </el-button>
      </div>
    </div>

    <!-- 统计卡片 -->
    <el-row :gutter="12" class="stat-row">
      <el-col :xs="12" :sm="8" :md="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-label">CI 实例总数</div>
          <div class="stat-value">{{ statsTotal }}</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-label">CI 类型数</div>
          <div class="stat-value">{{ ciTypes.length }}</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-label">关系类型数</div>
          <div class="stat-value">{{ relationTypeCount }}</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-label">当前页条数</div>
          <div class="stat-value">{{ cis.length }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" v-loading="loading">
      <el-table ref="tableRef" :data="cis" stripe border size="small"
                style="width: 100%" :row-key="rowKey" class="cmdb-table">
        <el-table-column type="index" label="#" width="50" fixed="left" class-name="not-draggable" />
        <el-table-column prop="name" label="名称" min-width="160" fixed="left" class-name="not-draggable">
          <template #default="{ row }">
            <b>{{ ciName(row) }}</b>
          </template>
        </el-table-column>
        <el-table-column prop="ci_type" label="CI 类型" width="120" class-name="not-draggable">
          <template #default="{ row }">
            <el-tag size="small">{{ row.ci_type_alias || row.ci_type || '-' }}</el-tag>
          </template>
        </el-table-column>
        <!-- 动态列：根据当前 CI 类型的字段自动生成，列名用中文别名 -->
        <el-table-column v-for="col in dynamicColumns" :key="col.prop"
                         :prop="col.prop" :label="col.label" :min-width="col.width"
                         :class-name="'cmdb-col-' + col.prop">
          <template #default="{ row }">
            <span :title="formatCell(row[col.prop])">{{ formatCell(row[col.prop]) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="90" class-name="not-draggable">
          <template #default="{ row }">
            <el-tag size="small" :type="statusType(row)">{{ row.status || '-' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" fixed="right" class-name="not-draggable">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="showDetail(row)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination" v-if="total > pageSize">
        <el-pagination v-model:current-page="page" v-model:page-size="pageSize"
                       :total="total" :page-sizes="[20, 50, 100, 200]"
                       layout="total, sizes, prev, pager, next"
                       @current-change="loadCis" @size-change="loadCis" />
      </div>
    </el-card>

    <!-- 详情抽屉 -->
    <el-drawer v-model="detailOpen" title="CI 详情" size="460px">
      <el-descriptions :column="1" border v-if="currentRow">
        <el-descriptions-item v-for="(v, k) in flatRow(currentRow)" :key="k" :label="k">
          <span class="detail-value">{{ formatVal(v) }}</span>
        </el-descriptions-item>
      </el-descriptions>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { Search } from '@element-plus/icons-vue'
import Sortable from 'sortablejs'
import api from '../../utils/api'

const loading = ref(false)
const cis = ref([])
const ciTypes = ref([])
const statsTotal = ref(0)
const relationTypeCount = ref(0)
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)
const cmdbUrl = ref('')
const filter = reactive({ ci_type: '', keyword: '' })
const detailOpen = ref(false)
const currentRow = ref(null)
const tableRef = ref(null)
// 属性别名映射 { 字段名: 中文别名 }
const attrAliases = ref({})
// 动态列顺序（拖拽排序后保存），按 ci_type 缓存
const columnOrderMap = reactive({})
// CI 类型 name -> unique_key 映射
const nameToUniqueKey = reactive({})

// 系统/内部字段，不展示为动态列
const SYSTEM_FIELDS = new Set([
  '_id', '_type', '_updated_at', '_updated_by',
  'ci_type', 'ci_type_alias', 'unique', 'unique_alias',
])

// 根据当前 CI 类型第一条数据动态生成列（列名用中文别名）
const dynamicColumns = computed(() => {
  if (!cis.value.length) return []
  const first = cis.value[0]
  const cols = []
  for (const key of Object.keys(first)) {
    if (SYSTEM_FIELDS.has(key)) continue
    if (key === first.unique) continue  // 名称已在固定列
    if (key === 'status') continue      // 状态已在固定列
    cols.push({
      prop: key,
      label: attrAliases.value[key] || key,
      width: 130,
    })
  }
  // 应用用户拖拽的列顺序
  const order = columnOrderMap[filter.ci_type]
  if (order && order.length) {
    const map = new Map(cols.map(c => [c.prop, c]))
    const sorted = []
    for (const prop of order) {
      if (map.has(prop)) sorted.push(map.get(prop))
    }
    // 追加未在排序中的列（新增字段）
    for (const c of cols) {
      if (!order.includes(c.prop)) sorted.push(c)
    }
    return sorted
  }
  return cols
})

function rowKey(row) {
  return row.id || row._id || row.mor || row.name || JSON.stringify(row).slice(0, 40)
}

function ciName(row) {
  const uk = row.unique
  if (uk && row[uk]) return row[uk]
  return row.name || row._id || '-'
}

function formatCell(val) {
  if (val === null || val === undefined || val === '') return '-'
  if (Array.isArray(val)) return val.length ? val.join(', ') : '-'
  if (typeof val === 'object') return JSON.stringify(val)
  return String(val)
}

function statusType(row) {
  const s = String(row.status || '').toLowerCase()
  if (s.includes('running') || s.includes('online') || s.includes('正常')) return 'success'
  if (s.includes('stop') || s.includes('offline') || s.includes('异常') || s.includes('故障')) return 'danger'
  if (s.includes('maintain') || s.includes('维护')) return 'warning'
  return 'info'
}

function flatRow(row) {
  // 详情抽屉的 label 也用中文别名
  const out = {}
  for (const [k, v] of Object.entries(row)) {
    if (v === null || v === undefined) continue
    const label = attrAliases.value[k] || k
    const val = typeof v === 'object' ? JSON.stringify(v, null, 2) : v
    out[label] = val
  }
  return out
}

function formatVal(v) {
  return v
}

function showDetail(row) {
  currentRow.value = row
  detailOpen.value = true
}

function openCmdb() {
  if (cmdbUrl.value) window.open(cmdbUrl.value, '_blank')
}

async function loadAll() {
  await Promise.all([loadConfig(), loadCiTypes(), loadRelationTypes(), loadCis()])
}

async function loadConfig() {
  try {
    const { data } = await api.get('/configs', { params: { type: 'cmdb' } })
    const cfg = (data || []).find((r) => r.provider === 'oneops' && r.enabled)
    cmdbUrl.value = (cfg && cfg.settings && cfg.settings.base_url) || ''
  } catch (e) {
    cmdbUrl.value = ''
  }
}

async function loadCiTypes() {
  try {
    const { data } = await api.get('/cmdb/ci-types')
    const items = data.items || []
    ciTypes.value = items.map((t) => {
      const uk = t.unique_key || t.name
      nameToUniqueKey[t.name] = uk
      return {
        value: t.name,          // 下拉值用类型名（属性接口需要）
        label: t.alias || t.name,
      }
    }).filter((t) => t.value)
  } catch (e) {
    ciTypes.value = []
  }
}

async function loadRelationTypes() {
  try {
    const { data } = await api.get('/cmdb/relation-types')
    relationTypeCount.value = (data.items || []).length
  } catch (e) {
    relationTypeCount.value = 0
  }
}

async function loadAttributes() {
  // 根据当前 CI 类型加载属性别名
  if (!filter.ci_type) {
    attrAliases.value = {}
    return
  }
  try {
    const { data } = await api.get('/cmdb/attributes', { params: { ci_type: filter.ci_type } })
    const items = data.items || []
    const map = {}
    for (const it of items) {
      if (it.name && it.alias) map[it.name] = it.alias
    }
    attrAliases.value = map
  } catch (e) {
    attrAliases.value = {}
  }
}

function onCiTypeChange() {
  page.value = 1
  loadAttributes()
  loadCis()
}

async function loadCis() {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize.value }
    // 搜索需要 unique_key，属性接口需要类型名
    const uk = filter.ci_type ? nameToUniqueKey[filter.ci_type] : ''
    if (uk) params.ci_type = uk
    if (filter.keyword) params.keyword = filter.keyword
    const { data } = await api.get('/cmdb/cis', { params })
    cis.value = data.items || []
    total.value = data.total || cis.value.length
    statsTotal.value = total.value
  } catch (e) {
    cis.value = []
    total.value = 0
  } finally {
    loading.value = false
    await nextTick()
    initSortable()
  }
}

// 初始化列拖拽排序
let sortableInstance = null
function initSortable() {
  if (!tableRef.value) return
  const el = tableRef.value.$el
  const headerRow = el.querySelector('.el-table__header-wrapper thead tr')
  if (!headerRow) return

  if (sortableInstance) sortableInstance.destroy()

  sortableInstance = Sortable.create(headerRow, {
    animation: 150,
    // 只允许拖动动态列区域（跳过固定的序号、名称、CI 类型、状态、操作列）
    filter: '.not-draggable',
    onEnd(evt) {
      if (evt.oldIndex === evt.newIndex) return
      // 从 th 的 class 中提取列名（cmdb-col-{prop}）
      const cells = headerRow.querySelectorAll('th')
      const newOrder = []
      cells.forEach((th) => {
        const cls = th.className || ''
        const m = cls.match(/cmdb-col-(\S+)/)
        if (m) newOrder.push(m[1])
      })
      columnOrderMap[filter.ci_type] = newOrder
    },
  })
}

onMounted(loadAll)
</script>

<style scoped>
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 14px;
}
.page-title {
  margin: 0;
}
.filters {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}
.stat-row {
  margin-bottom: 14px;
}
.stat-card {
  text-align: center;
}
.stat-label {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.stat-value {
  font-size: 26px;
  font-weight: 700;
  margin-top: 6px;
  color: var(--el-color-primary);
}
.pagination {
  margin-top: 14px;
  display: flex;
  justify-content: flex-end;
}
.detail-value {
  white-space: pre-wrap;
  word-break: break-all;
}
.cmdb-table :deep(.el-table__header th) {
  cursor: move;
}
</style>
