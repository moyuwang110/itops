<template>
  <div class="page-container">
    <h2 class="page-title">虚拟机管理</h2>

    <el-card shadow="never">
      <div class="toolbar">
        <el-input v-model="keyword" placeholder="虚拟机名称 / 主机名 / IP" clearable
                  style="width: 260px" :prefix-icon="Search" @keyup.enter="handleSearch" />
        <el-select v-model="powerFilter" placeholder="电源状态" clearable style="width: 140px" @change="handleSearch">
          <el-option label="已开机" value="poweredOn" />
          <el-option label="已关机" value="poweredOff" />
          <el-option label="已挂起" value="suspended" />
        </el-select>
        <el-button type="primary" :icon="Search" @click="handleSearch">查询</el-button>
        <span class="flex-grow" />
        <span class="text-muted col-hint">拖动表头可排序，拖动列边框可调整宽度</span>
        <el-button link type="primary" @click="resetColumns">重置列设置</el-button>
        <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
      </div>

      <el-row :gutter="14" class="stat-row">
        <el-col :span="6">
          <el-statistic title="虚拟机总数" :value="summary.total" />
        </el-col>
        <el-col :span="6">
          <el-statistic title="已开机" :value="summary.powered_on" />
        </el-col>
        <el-col :span="6">
          <el-statistic title="已关机" :value="summary.powered_off" />
        </el-col>
        <el-col :span="6">
          <el-statistic title="已挂起" :value="summary.suspended" />
        </el-col>
      </el-row>

      <el-table ref="tableRef" :data="filtered" v-loading="loading" stripe border
                style="width: 100%; margin-top: 14px"
                :default-sort="{ prop: 'name', order: 'ascending' }"
                @header-dragend="onHeaderDragend">
        <el-table-column v-for="col in columns" :key="col.key"
                         :column-key="col.key"
                         :prop="col.prop" :label="col.label"
                         :width="col.width" :min-width="col.minWidth"
                         :align="col.align" :sortable="col.sortable"
                         show-overflow-tooltip>
          <template #default="{ row }">
            <el-tag v-if="col.key === 'power_state'" :type="powerTagType(row.power_state)" size="small">
              {{ powerLabel(row.power_state) }}
            </el-tag>
            <span v-else-if="col.key === 'num_cpu'">{{ row.num_cpu }}</span>
            <span v-else-if="col.key === 'memory_mb'">{{ ((row.memory_mb || 0) / 1024).toFixed(1) }}</span>
            <span v-else-if="col.key === 'overall_status'">
              <el-tag :type="statusTagType(row.overall_status)" size="small">{{ row.overall_status || '-' }}</el-tag>
            </span>
            <span v-else-if="col.key === 'guest_ip'" class="mono">{{ row.guest_ip || '-' }}</span>
            <span v-else>{{ row[col.prop] || '-' }}</span>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无虚拟机数据" />
        </template>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { Refresh, Search } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import Sortable from 'sortablejs'
import api from '../../utils/api'

const STORAGE_ORDER = 'itops.vms.columnOrder'
const STORAGE_WIDTH = 'itops.vms.columnWidth'

const defaultColumns = [
  { key: 'name', label: '虚拟机名称', prop: 'name', minWidth: 180, sortable: true },
  { key: 'power_state', label: '电源状态', width: 100 },
  { key: 'guest_hostname', label: '客户机主机名', prop: 'guest_hostname', minWidth: 160 },
  { key: 'guest_ip', label: 'IP 地址', prop: 'guest_ip', minWidth: 140 },
  { key: 'guest_os', label: '操作系统', prop: 'guest_os', minWidth: 200 },
  { key: 'num_cpu', label: 'CPU', width: 80, align: 'center' },
  { key: 'memory_mb', label: '内存(GB)', width: 100, align: 'center' },
  { key: 'resource_pool', label: '资源池', prop: 'resource_pool', minWidth: 120 },
  { key: 'overall_status', label: '整体状态', width: 110 },
]

const rows = ref([])
const summary = ref({ total: 0, powered_on: 0, powered_off: 0, suspended: 0 })
const loading = ref(false)
const keyword = ref('')
const powerFilter = ref('')
const tableRef = ref(null)
let sortable = null

function loadWidths() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_WIDTH) || '{}')
  } catch { return {} }
}

function loadOrder() {
  try {
    const raw = JSON.parse(localStorage.getItem(STORAGE_ORDER) || '[]')
    return Array.isArray(raw) ? raw : []
  } catch { return [] }
}

function buildColumns() {
  const widths = loadWidths()
  const order = loadOrder()
  const map = new Map(defaultColumns.map((c) => [c.key, { ...c }]))
  for (const c of map.values()) {
    if (widths[c.key]) {
      c.width = widths[c.key]
    }
  }
  const ordered = []
  for (const key of order) {
    if (map.has(key)) {
      ordered.push(map.get(key))
      map.delete(key)
    }
  }
  ordered.push(...map.values())
  return ordered
}

const columns = ref(buildColumns())

const filtered = computed(() => {
  let list = rows.value
  if (powerFilter.value) {
    list = list.filter((v) => v.power_state === powerFilter.value)
  }
  if (keyword.value.trim()) {
    const kw = keyword.value.trim().toLowerCase()
    list = list.filter((v) =>
      (v.name || '').toLowerCase().includes(kw) ||
      (v.guest_hostname || '').toLowerCase().includes(kw) ||
      (v.guest_ip || '').toLowerCase().includes(kw)
    )
  }
  return list
})

function powerLabel(s) {
  return { poweredOn: '已开机', poweredOff: '已关机', suspended: '已挂起' }[s] || s || '-'
}
function powerTagType(s) {
  return { poweredOn: 'success', poweredOff: 'info', suspended: 'warning' }[s] || 'info'
}
function statusTagType(s) {
  return { green: 'success', yellow: 'warning', red: 'danger', gray: 'info' }[s] || 'info'
}

function handleSearch() {
  // 前端过滤，无需重新请求
}

function onHeaderDragend(newWidth, oldWidth, column) {
  const key = column.columnKey
  if (!key) return
  const widths = loadWidths()
  widths[key] = Math.round(newWidth)
  localStorage.setItem(STORAGE_WIDTH, JSON.stringify(widths))
  const target = columns.value.find((c) => c.key === key)
  if (target) target.width = widths[key]
}

function resetColumns() {
  localStorage.removeItem(STORAGE_ORDER)
  localStorage.removeItem(STORAGE_WIDTH)
  columns.value = defaultColumns.map((c) => ({ ...c }))
  ElMessage.success('列设置已重置')
  nextTick(initSortable)
}

function saveOrder() {
  localStorage.setItem(STORAGE_ORDER, JSON.stringify(columns.value.map((c) => c.key)))
}

function initSortable() {
  destroySortable()
  const root = tableRef.value?.$el
  const tr = root?.querySelector('.el-table__header-wrapper thead tr')
  if (!tr) return
  sortable = Sortable.create(tr, {
    animation: 150,
    draggable: 'th',
    filter: (evt, target) => target.classList.contains('gutter'),
    onEnd: ({ oldIndex, newIndex }) => {
      if (oldIndex === newIndex) return
      const list = columns.value.slice()
      const [moved] = list.splice(oldIndex, 1)
      list.splice(newIndex, 0, moved)
      columns.value = list
      saveOrder()
      // 重新渲染后重新绑定
      nextTick(initSortable)
    },
  })
}

function destroySortable() {
  if (sortable) {
    sortable.destroy()
    sortable = null
  }
}

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/vmware/vms')
    rows.value = data.vms || []
    summary.value = {
      total: data.total || 0,
      powered_on: data.powered_on || 0,
      powered_off: data.powered_off || 0,
      suspended: data.suspended || 0,
    }
    await nextTick()
    initSortable()
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '获取虚拟机列表失败')
  } finally {
    loading.value = false
  }
}

onMounted(load)
onBeforeUnmount(destroySortable)
</script>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.flex-grow {
  flex: 1;
}
.col-hint {
  font-size: 12px;
}
.stat-row {
  margin-top: 14px;
}
</style>
