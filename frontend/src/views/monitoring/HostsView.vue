<template>
  <div class="page-container">
    <h2 class="page-title">主机</h2>

    <el-card shadow="never">
      <div class="toolbar">
        <el-input v-model="keyword" placeholder="主机名 / IP 关键字" clearable
                  style="width: 240px" :prefix-icon="Search" @keyup.enter="load" />
        <el-select v-model="availFilter" placeholder="Agent 可用性" clearable style="width: 150px">
          <el-option label="可用" value="1" />
          <el-option label="不可用" value="2" />
          <el-option label="未知" value="0" />
        </el-select>
        <el-button type="primary" :icon="Search" :loading="loading" @click="load">查询</el-button>
        <span class="flex-grow" />
        <span class="text-muted">共 {{ filtered.length }} 台主机</span>
        <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
      </div>

      <el-table :data="filtered" v-loading="loading" stripe border style="width: 100%; margin-top: 14px">
        <el-table-column prop="host" label="主机名" min-width="160" show-overflow-tooltip sortable />
        <el-table-column prop="ip" label="IP 地址" width="140" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="mono">{{ row.ip || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="主机组" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <el-tag v-for="g in row.hostgroups" :key="g" size="small" effect="plain"
                    style="margin-right: 4px; margin-bottom: 2px">{{ g }}</el-tag>
            <span v-if="!row.hostgroups || !row.hostgroups.length" class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="Zabbix 可用性" width="120" align="center">
          <template #default="{ row }">
            <el-tooltip :content="row.error || row.available_label" placement="top">
              <el-tag :type="availTag(row.available)" size="small">{{ row.available_label }}</el-tag>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="CPU 使用" width="170">
          <template #default="{ row }">
            <usage-bar :value="row.cpu_usage" />
          </template>
        </el-table-column>
        <el-table-column label="内存使用" width="170">
          <template #default="{ row }">
            <usage-bar :value="row.memory_usage" />
          </template>
        </el-table-column>
        <el-table-column label="磁盘使用" width="170">
          <template #default="{ row }">
            <usage-bar :value="row.disk_usage" />
          </template>
        </el-table-column>
        <el-table-column label="监控状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'" size="small" effect="plain">
              {{ row.enabled ? '已启用' : '已停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无主机数据（请检查 Zabbix 集成配置）" />
        </template>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { computed, h, onMounted, ref } from 'vue'
import { Refresh, Search } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import api from '../../utils/api'

const rows = ref([])
const loading = ref(false)
const keyword = ref('')
const availFilter = ref('')

const filtered = computed(() => {
  let list = rows.value
  if (availFilter.value !== '' && availFilter.value !== null) {
    list = list.filter((h) => String(h.available) === String(availFilter.value))
  }
  return list
})

function availTag(v) {
  return { '1': 'success', '2': 'danger', '0': 'info' }[String(v)] || 'info'
}

// 使用率进度条渲染组件（避免重复模板）
const UsageBar = {
  props: { value: { type: [Number, String], default: null } },
  setup(props) {
    return () => {
      if (props.value === null || props.value === undefined || props.value === '') {
        return h('span', { class: 'text-muted' }, '-')
      }
      const val = Number(props.value)
      const color = val >= 85 ? '#f56c6c' : val >= 70 ? '#e6a23c' : '#67c23a'
      return h('div', { style: 'display:flex;align-items:center;gap:8px' }, [
        h('div', { style: 'flex:1' }, [
          h('div', {
            style: `height:8px;border-radius:4px;background:rgba(144,147,153,.2);overflow:hidden`,
          }, [
            h('div', {
              style: `height:100%;width:${Math.min(val, 100)}%;background:${color};border-radius:4px`,
            }),
          ]),
        ]),
        h('span', { style: 'width:42px;text-align:right;font-size:12px' }, `${val}%`),
      ])
    }
  },
}

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/zabbix/hosts-overview', { params: { keyword: keyword.value.trim() } })
    rows.value = data || []
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '获取主机列表失败')
  } finally {
    loading.value = false
  }
}

onMounted(load)
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
</style>
