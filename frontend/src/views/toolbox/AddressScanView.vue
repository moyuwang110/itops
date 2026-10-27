<template>
  <!-- 地址扫描页面 v2 - 仿 IPAM 子网管理界面 -->
  <div class="page-container">
    <h2 class="page-title">地址扫描</h2>

    <!-- 子网信息与操作 -->
    <el-card shadow="never" class="subnet-card">
      <div class="subnet-head">
        <div class="subnet-info">
          <el-input v-model="cidr" placeholder="CIDR，如 192.168.1.0/24" clearable style="width:220px"
                    @keyup.enter="doScan" />
          <el-button type="primary" :icon="Search" :loading="scanning" @click="doScan">立即扫描</el-button>
        </div>
        <div class="subnet-meta" v-if="result.cidr">
          <span class="meta-gateway">{{ result.gateway }}</span>
          <el-tag type="success" size="small" effect="plain">已启用</el-tag>
          <span class="text-muted">{{ result.cidr }}</span>
          <span class="text-muted">掩码 {{ result.netmask }}</span>
        </div>
      </div>

      <!-- 统计栏 -->
      <div class="stats-bar" v-if="result.total">
        <div class="stat-item" data-kind="total">
          <span class="stat-num">{{ result.total }}</span><span class="stat-label">总数</span>
        </div>
        <div class="stat-item" data-kind="used">
          <span class="stat-num">{{ result.used }}</span><span class="stat-label">已用</span>
        </div>
        <div class="stat-item" data-kind="free">
          <span class="stat-num">{{ result.free }}</span><span class="stat-label">空闲</span>
        </div>
        <div class="stat-item" data-kind="unknown">
          <span class="stat-num">{{ result.unknown }}</span><span class="stat-label">未知</span>
        </div>
        <div class="stat-item" data-kind="conflict">
          <span class="stat-num">{{ result.conflict }}</span><span class="stat-label">冲突</span>
        </div>
        <div class="stat-item" data-kind="usage">
          <span class="stat-num">{{ result.utilization }}%</span><span class="stat-label">利用率</span>
        </div>
      </div>

      <div class="scan-time text-muted" v-if="result.last_scan">
        最近扫描：{{ result.last_scan }}（已完成）
      </div>

      <!-- 筛选与搜索 -->
      <div class="filter-bar" v-if="result.total">
        <span class="filter-label">筛选状态：</span>
        <el-select v-model="statusFilter" size="small" style="width:120px">
          <el-option label="全部" value="all" />
          <el-option label="已用" value="used" />
          <el-option label="空闲" value="free" />
          <el-option label="未知" value="unknown" />
          <el-option label="冲突" value="conflict" />
        </el-select>
        <el-input v-model="keyword" size="small" placeholder="搜索 IP / MAC / 主机名" clearable
                  style="width:240px" />
        <span class="count-text">共 {{ filteredAddresses.length }} / {{ result.total }} 个地址</span>
      </div>

      <!-- 地址网格 -->
      <div class="address-grid" v-if="filteredAddresses.length">
        <div v-for="addr in filteredAddresses" :key="addr.ip" class="cell-wrap">
          <div class="address-cell" :class="addr.status" :data-status="addr.status">
            <span class="cell-num">{{ addr.ip.split('.').pop() }}</span>
            <span class="cell-icon">{{ STATUS_ICON[addr.status] || '' }}</span>
          </div>
          <div class="cell-tooltip">
            <div class="tt-head">
              <strong>{{ addr.ip }}</strong>
              <span class="tt-badge" :class="addr.status">{{ STATUS_LABEL[addr.status] }}</span>
            </div>
            <dl class="tt-dl">
              <dt>主机号</dt><dd>{{ addr.ip.split('.').pop() }}</dd>
              <dt>MAC 地址</dt><dd>{{ addr.mac || '未知' }}</dd>
              <dt>主机名</dt><dd>{{ addr.hostname || '未知' }}</dd>
              <dt>开放端口</dt>
              <dd>{{ addr.open_ports && addr.open_ports.length ? addr.open_ports.join(', ') : (addr.status === 'free' ? '无' : '未知') }}</dd>
              <dt>响应时间</dt><dd>{{ addr.response_ms != null ? addr.response_ms + ' ms' : '未知' }}</dd>
              <dt>探测来源</dt><dd>{{ addr.source || '未知' }}</dd>
              <dt>探测时间</dt><dd>{{ addr.discovered_at || '—' }}</dd>
              <template v-if="addr.note">
                <dt>备注</dt><dd class="tt-note">{{ addr.note }}</dd>
              </template>
            </dl>
          </div>
        </div>
      </div>

      <el-empty v-if="result.total === 0" description="输入 CIDR 后点击立即扫描" />
    </el-card>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { Search } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import api from '../../utils/api'

const STATUS_LABEL = { used: '已用', free: '空闲', unknown: '未知', conflict: '冲突' }
const STATUS_ICON = { used: '●', free: '○', unknown: '?', conflict: '!' }

const cidr = ref('192.168.1.0/24')
const scanning = ref(false)
const statusFilter = ref('all')
const keyword = ref('')
const result = reactive({
  cidr: '', gateway: '', netmask: '', total: 0, used: 0, free: 0,
  unknown: 0, conflict: 0, utilization: 0, last_scan: '', addresses: [],
})

const filteredAddresses = computed(() => {
  let list = result.addresses
  if (statusFilter.value !== 'all') {
    list = list.filter(a => a.status === statusFilter.value)
  }
  const kw = keyword.value.trim().toLowerCase()
  if (kw) {
    list = list.filter(a =>
      a.ip.includes(kw) || (a.mac || '').toLowerCase().includes(kw) || (a.hostname || '').toLowerCase().includes(kw)
    )
  }
  return list
})

async function doScan() {
  if (!cidr.value.trim()) {
    ElMessage.warning('请输入 CIDR 地址')
    return
  }
  scanning.value = true
  try {
    const { data } = await api.get('/network-tools/scan', { params: { cidr: cidr.value.trim() } })
    Object.assign(result, data)
    if (data.used === 0) {
      ElMessage.info('未发现存活主机')
    }
  } finally {
    scanning.value = false
  }
}
</script>

<style scoped>
.subnet-card { border-radius: 8px; }

.subnet-head {
  display: flex; flex-wrap: wrap; align-items: center; gap: 16px; margin-bottom: 14px;
}
.subnet-info { display: flex; gap: 10px; align-items: center; }
.subnet-meta { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.meta-gateway { font-size: 18px; font-weight: 600; }

/* 统计栏 — 网格平铺布局，每个统计项为独立卡片 */
.stats-bar {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
  gap: 10px;
  padding: 14px 0;
  border-top: 1px solid var(--el-border-color-lighter);
  border-bottom: 1px solid var(--el-border-color-lighter);
  margin-bottom: 12px;
}
.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 12px 8px;
  background: var(--el-fill-color-light);
  border-radius: 8px;
  border: 1px solid var(--el-border-color-lighter);
}
.stat-num {
  font-size: 22px;
  font-weight: 700;
  color: var(--el-text-color-primary);
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
}
.stat-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  letter-spacing: 0.04em;
}

.stat-item[data-kind="used"] .stat-num::before { content: "● "; color: #22c55e; }
.stat-item[data-kind="free"] .stat-num::before { content: "○ "; color: #94a3b8; }
.stat-item[data-kind="unknown"] .stat-num::before { content: "? "; color: #a78bfa; }
.stat-item[data-kind="conflict"] .stat-num::before { content: "! "; color: #f97316; }
.stat-item[data-kind="total"] .stat-num::before { content: "▦ "; color: var(--el-text-color-secondary); }
.stat-item[data-kind="usage"] .stat-num::before { content: "▲ "; color: var(--el-color-primary); }

.scan-time { margin-bottom: 12px; }

.filter-bar {
  display: flex; align-items: center; gap: 10px; margin-bottom: 12px; flex-wrap: wrap;
}
.filter-label { font-size: 13px; color: var(--el-text-color-regular); }
.count-text { margin-left: auto; font-size: 13px; color: var(--el-text-color-secondary); }

/* 地址网格 */
.address-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(48px, 1fr)); gap: 4px;
}
.cell-wrap { position: relative; }
.cell-wrap:hover .cell-tooltip { opacity: 1; visibility: visible; }

.address-cell {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  height: 38px; border-radius: 4px; cursor: pointer; user-select: none;
  border: 2px solid transparent; transition: transform 0.1s, border-color 0.1s;
  background: var(--el-fill-color-light);
}
.address-cell:hover { transform: translateY(-1px); border-color: var(--el-color-primary); }
.cell-num { font-size: 12px; font-weight: 600; font-variant-numeric: tabular-nums; line-height: 1.1; }
.cell-icon { font-size: 8px; opacity: 0.7; line-height: 1; margin-top: 1px; }

.address-cell.used {
  background: rgba(34, 197, 94, 0.85); color: #04190b;
  border-color: rgba(34, 197, 94, 0.95);
}
.address-cell.free { background: rgba(148, 163, 184, 0.55); color: var(--el-text-color-primary); }
.address-cell.unknown { background: rgba(167, 139, 250, 0.75); color: #1a0e3f; }
.address-cell.conflict {
  background: rgba(249, 115, 22, 0.9); color: #1a0a02;
  border-color: rgba(249, 115, 22, 1);
  outline: 2px dashed rgba(0, 0, 0, 0.25); outline-offset: -4px;
}

/* 自定义 tooltip */
.cell-tooltip {
  position: absolute; bottom: calc(100% + 6px); left: 50%; transform: translateX(-50%);
  z-index: 50; background: var(--el-bg-color); border: 1px solid var(--el-border-color);
  border-radius: 10px; padding: 10px 12px; font-size: 12px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2); min-width: 260px; pointer-events: none;
  opacity: 0; visibility: hidden; transition: opacity 0.12s ease;
}
.tt-head {
  display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;
  padding-bottom: 6px; border-bottom: 1px solid var(--el-border-color-lighter);
}
.tt-badge { font-size: 11px; padding: 2px 8px; border-radius: 999px; font-weight: 600; }
.tt-badge.used { background: rgba(34, 197, 94, 0.18); color: #16a34a; }
.tt-badge.free { background: rgba(148, 163, 184, 0.25); color: #64748b; }
.tt-badge.unknown { background: rgba(167, 139, 250, 0.18); color: #7c3aed; }
.tt-badge.conflict { background: rgba(249, 115, 22, 0.2); color: #ea580c; }
.tt-dl { display: grid; grid-template-columns: max-content 1fr; gap: 3px 10px; margin: 0; }
.tt-dl dt { color: var(--el-text-color-secondary); }
.tt-dl dd { margin: 0; word-break: break-all; color: var(--el-text-color-primary); }
.tt-note { color: var(--el-color-warning) !important; }
</style>
