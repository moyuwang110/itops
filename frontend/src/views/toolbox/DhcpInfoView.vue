<template>
  <div class="page-container">
    <h2 class="page-title">DHCP 信息</h2>

    <el-card shadow="never" class="tool-card">
      <div class="card-header">
        <span class="card-title"><el-icon><Promotion /></el-icon> DHCP 租约信息</span>
        <div class="header-actions">
          <el-select
            v-model="query.server"
            placeholder="选择 DHCP 服务器"
            clearable
            size="small"
            style="width:200px"
            @change="onServerChange"
          >
            <el-option
              v-for="s in dhcpInfo.servers"
              :key="s.id"
              :label="`${s.display_name}（${s.count}条）`"
              :value="s.id"
            />
          </el-select>
          <el-select v-model="query.state" placeholder="状态" clearable size="small" style="width:130px" @change="loadDhcp">
            <el-option v-for="s in stateOptions" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
          <el-input
            v-model="query.q"
            placeholder="搜索 IP / 主机名 / MAC / 姓名"
            clearable
            size="small"
            style="width:240px"
            @keyup.enter="loadDhcp"
            @clear="loadDhcp"
          >
            <template #append>
              <el-button :icon="Search" @click="loadDhcp" />
            </template>
          </el-input>
          <el-dropdown @command="handleExport">
            <el-button size="small" :icon="Download">导出</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="csv">导出 CSV</el-dropdown-item>
                <el-dropdown-item command="xlsx">导出 XLSX</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-button size="small" :icon="Edit" @click="openNamemap">姓名映射</el-button>
          <el-button :icon="Refresh" size="small" :loading="loading" @click="loadDhcp">刷新</el-button>
        </div>
      </div>

      <div class="meta-bar">
        <span class="text-muted" v-if="dhcpInfo.lease_source">来源：{{ dhcpInfo.lease_source }}</span>
        <span class="text-muted" v-if="dhcpInfo.collected_at">采集时间：{{ dhcpInfo.collected_at }}</span>
        <span class="text-muted">共 {{ dhcpInfo.total }} 条</span>
      </div>

      <!-- DHCP 租约列表 -->
      <el-table
        :data="dhcpInfo.leases"
        size="small"
        stripe
        height="420"
        @sort-change="onSortChange"
        :default-sort="{ prop: 'ip', order: 'ascending' }"
      >
        <el-table-column prop="hostname" label="主机名" min-width="160" show-overflow-tooltip sortable="custom">
          <template #default="{ row }">{{ row.hostname || '-' }}</template>
        </el-table-column>
        <el-table-column prop="state" label="状态" width="100" sortable="custom">
          <template #default="{ row }">
            <el-tag :type="stateTagType(row.state)" size="small" effect="light">{{ stateLabel(row.state) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="ends" label="租期" width="170" sortable="custom">
          <template #default="{ row }">{{ row.ends || '-' }}</template>
        </el-table-column>
        <el-table-column prop="mac" label="MAC 地址" width="180" sortable="custom">
          <template #default="{ row }">
            <span class="mac-text">{{ row.mac || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="ip" label="IP 地址" width="150" sortable="custom" />
        <el-table-column prop="name" label="姓名" width="110">
          <template #default="{ row }">{{ row.name || '-' }}</template>
        </el-table-column>
        <template #empty>
          <el-empty description="未发现 DHCP 租约文件或租约为空" :image-size="60" />
        </template>
      </el-table>

      <div class="pagination-bar">
        <el-pagination
          v-model:current-page="query.page"
          v-model:page-size="query.page_size"
          :page-sizes="[20, 50, 100, 200]"
          :total="dhcpInfo.total"
          layout="total, sizes, prev, pager, next, jumper"
          background
          small
          @size-change="loadDhcp"
          @current-change="loadDhcp"
        />
      </div>

      <!-- 本机网卡信息 -->
      <div class="section-label" style="margin-top:18px">本机网卡</div>
      <el-table :data="dhcpInfo.interfaces" size="small" stripe>
        <el-table-column prop="name" label="网卡" width="180" />
        <el-table-column prop="ip" label="IP / 掩码" width="200" />
        <el-table-column prop="mac" label="MAC 地址" width="180">
          <template #default="{ row }"><span class="mac-text">{{ row.mac || '-' }}</span></template>
        </el-table-column>
        <template #empty><el-empty description="未获取到网卡信息" :image-size="60" /></template>
      </el-table>
    </el-card>

    <!-- 姓名映射弹窗 -->
    <el-dialog v-model="namemapVisible" title="姓名映射管理" width="640px" @open="loadNamemap">
      <div class="namemap-tip">
        将 主机名 / IP / MAC 映射到人员姓名，便于快速定位设备使用人。
      </div>
      <div class="namemap-add">
        <el-input v-model="nmKey" placeholder="主机名 / IP / MAC" size="small" style="width:220px" />
        <el-input v-model="nmName" placeholder="姓名" size="small" style="width:140px" />
        <el-button type="primary" size="small" :loading="nmSaving" @click="addNamemap">添加</el-button>
      </div>
      <el-table :data="namemapList" size="small" stripe max-height="360" style="margin-top:12px">
        <el-table-column prop="key" label="键（主机名/IP/MAC）" min-width="220" />
        <el-table-column prop="name" label="姓名" width="180" />
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-button type="danger" link size="small" @click="delNamemap(row.key)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty><el-empty description="暂无映射" :image-size="50" /></template>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Promotion, Refresh, Search, Download, Edit } from '@element-plus/icons-vue'
import api from '../../utils/api'

const loading = ref(false)
const dhcpInfo = reactive({
  lease_source: '',
  collected_at: '',
  current_server: '',
  servers: [],
  total: 0,
  page: 1,
  page_size: 50,
  lease_count: 0,
  leases: [],
  interfaces: [],
  states: [],
})

const query = reactive({
  server: '',
  q: '',
  state: '',
  sort_by: 'ip',
  sort_dir: 'asc',
  page: 1,
  page_size: 50,
})

const stateOptions = [
  { label: 'Active', value: 'active' },
  { label: 'Inactive', value: 'inactive' },
  { label: 'Reserved', value: 'reserved' },
  { label: 'Declined', value: 'declined' },
]

const stateMap = { active: 'Active', inactive: 'Inactive', reserved: 'Reserved', declined: 'Declined' }
function stateLabel(s) { return stateMap[s] || (s || '-') }
function stateTagType(s) {
  switch (s) {
    case 'active': return 'success'
    case 'inactive': return 'info'
    case 'reserved': return 'warning'
    case 'declined': return 'danger'
    default: return ''
  }
}

async function loadDhcp() {
  loading.value = true
  try {
    const { data } = await api.get('/network-tools/dhcp', { params: query })
    Object.assign(dhcpInfo, data)
    // 同步当前服务器到选择器
    if (data.current_server && !query.server) {
      query.server = data.current_server
    }
  } catch (e) {
    ElMessage.error('加载 DHCP 信息失败')
  } finally {
    loading.value = false
  }
}

function onServerChange() {
  query.page = 1
  loadDhcp()
}

function onSortChange({ prop, order }) {
  if (!prop) return
  query.sort_by = prop
  query.sort_dir = order === 'descending' ? 'desc' : 'asc'
  loadDhcp()
}

function handleExport(fmt) {
  const params = new URLSearchParams({ server: query.server, q: query.q, state: query.state, fmt })
  const url = `/api/v1/network-tools/dhcp/export?${params}`
  fetch(url, { credentials: 'include' })
    .then(r => {
      if (!r.ok) throw new Error('导出失败')
      return r.blob()
    })
    .then(blob => {
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `dhcp_leases.${fmt}`
      a.click()
      URL.revokeObjectURL(a.href)
    })
    .catch(() => ElMessage.error('导出失败'))
}

// 姓名映射
const namemapVisible = ref(false)
const namemapList = ref([])
const nmKey = ref('')
const nmName = ref('')
const nmSaving = ref(false)

async function loadNamemap() {
  const { data } = await api.get('/network-tools/dhcp/namemap')
  namemapList.value = data.items || []
}

async function addNamemap() {
  if (!nmKey.value.trim() || !nmName.value.trim()) {
    ElMessage.warning('请填写键与姓名')
    return
  }
  nmSaving.value = true
  try {
    await api.post('/network-tools/dhcp/namemap', { key: nmKey.value, name: nmName.value })
    ElMessage.success('已添加')
    nmKey.value = ''
    nmName.value = ''
    await loadNamemap()
    loadDhcp()
  } finally {
    nmSaving.value = false
  }
}

async function delNamemap(key) {
  try {
    await ElMessageBox.confirm(`确认删除映射「${key}」？`, '提示', { type: 'warning' })
    await api.delete('/network-tools/dhcp/namemap', { params: { key } })
    ElMessage.success('已删除')
    await loadNamemap()
    loadDhcp()
  } catch (e) { /* 用户取消 */ }
}

function openNamemap() {
  namemapVisible.value = true
}

onMounted(() => {
  loadDhcp()
})
</script>

<style scoped>
.tool-card { border-radius: 8px; }

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}

.card-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.meta-bar {
  display: flex;
  justify-content: space-between;
  margin-bottom: 10px;
}

.mac-text {
  font-family: 'SFMono-Regular', Consolas, monospace;
  font-size: 12px;
}

.pagination-bar {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}

.section-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-regular);
  margin-bottom: 8px;
}

.namemap-tip {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin-bottom: 12px;
}

.namemap-add {
  display: flex;
  gap: 8px;
  align-items: center;
}
</style>
