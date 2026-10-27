<template>
  <div class="page-container">
    <h2 class="page-title">IPAM 地址管理</h2>

    <!-- 冲突告警栏 -->
    <el-alert v-if="conflicts.length" type="error" :closable="false" show-icon class="conflict-banner">
      <template #title>
        <span class="conflict-title">检测到 {{ conflicts.length }} 个 IP 地址冲突</span>
        <el-button link type="primary" style="margin-left: 10px" @click="focusConflict">
          查看冲突地址
        </el-button>
      </template>
      <div class="conflict-list">
        <el-tag v-for="c in conflicts.slice(0, 8)" :key="c.id" type="danger" effect="plain" size="small"
                class="conflict-tag" @click="jumpToConflict(c)">
          {{ c.ip }} · {{ c.conflict_reason }}
        </el-tag>
        <span v-if="conflicts.length > 8" class="text-muted">等 {{ conflicts.length }} 项</span>
      </div>
    </el-alert>

    <el-tabs v-model="activeTab" class="ipam-tabs">
      <!-- ========== 网段管理 ========== -->
      <el-tab-pane label="网段管理" name="subnets">
        <el-row :gutter="14">
          <el-col :xs="24" :md="8" :lg="7">
            <el-card shadow="never" class="subnet-panel">
              <template #header>
                <div class="card-header-flex">
                  <span>网段列表</span>
                  <el-button type="primary" size="small" :icon="Plus" @click="openSubnetDialog()">新建网段</el-button>
                </div>
              </template>
              <div v-loading="subnetLoading" class="subnet-list">
                <div v-for="s in subnets" :key="s.id"
                     class="subnet-item" :class="{ active: selectedSubnetId === s.id }"
                     @click="selectSubnet(s)">
                  <div class="subnet-head">
                    <span class="subnet-name">{{ s.name || s.cidr }}</span>
                    <el-tag v-if="s.vlan_id" size="small" effect="plain">VLAN {{ s.vlan_id }}</el-tag>
                  </div>
                  <div class="subnet-cidr mono">{{ s.cidr }}</div>
                  <el-progress :percentage="Math.min(s.utilization || 0, 100)"
                               :stroke-width="6"
                               :color="s.utilization >= 85 ? '#f56c6c' : s.utilization >= 70 ? '#e6a23c' : '#409eff'" />
                  <div class="subnet-meta">
                    <span>已用 {{ s.used }} / {{ s.total }}</span>
                    <span v-if="s.conflict" class="text-danger">冲突 {{ s.conflict }}</span>
                  </div>
                  <div class="subnet-actions" @click.stop>
                    <el-button link type="primary" size="small" :loading="scanningId === s.id" @click="scanSubnet(s)">扫描</el-button>
                    <el-button link type="primary" size="small" @click="openSubnetDialog(s)">编辑</el-button>
                    <el-button link type="danger" size="small" @click="removeSubnet(s)">删除</el-button>
                  </div>
                </div>
                <el-empty v-if="!subnets.length" description="尚未创建网段" :image-size="60" />
              </div>
            </el-card>
          </el-col>

          <el-col :xs="24" :md="16" :lg="17">
            <el-card shadow="never">
              <template #header>
                <div class="card-header-flex">
                  <span>
                    {{ currentSubnet ? `${currentSubnet.name || currentSubnet.cidr} · 地址明细` : '地址明细' }}
                  </span>
                  <div v-if="currentSubnet">
                    <el-button size="small" :icon="Refresh" :loading="scanningId === currentSubnet.id"
                               @click="scanSubnet(currentSubnet)">立即扫描</el-button>
                    <el-button size="small" type="primary" :icon="Plus" @click="openAssignDialog">手工登记</el-button>
                  </div>
                </div>
              </template>

              <template v-if="currentSubnet">
                <el-row :gutter="12" class="stat-row">
                  <el-col :span="4"><el-statistic title="地址总数" :value="currentSubnet.total" /></el-col>
                  <el-col :span="4"><el-statistic title="已使用" :value="currentSubnet.used" /></el-col>
                  <el-col :span="4"><el-statistic title="空闲" :value="currentSubnet.free" /></el-col>
                  <el-col :span="4"><el-statistic title="已登记" :value="currentSubnet.reserved" /></el-col>
                  <el-col :span="4"><el-statistic title="冲突" :value="currentSubnet.conflict" /></el-col>
                  <el-col :span="4"><el-statistic title="利用率" :value="currentSubnet.utilization" suffix="%" /></el-col>
                </el-row>

                <div class="toolbar" style="margin-top: 12px">
                  <el-input v-model="addrKeyword" placeholder="IP / MAC / 主机名 / 责任人" clearable
                            style="width: 220px" :prefix-icon="Search" @keyup.enter="loadAddresses" />
                  <el-select v-model="addrStatus" placeholder="状态" clearable style="width: 120px" @change="loadAddresses">
                    <el-option v-for="(label, key) in statusLabels" :key="key" :label="label" :value="key" />
                  </el-select>
                  <el-checkbox v-model="onlyConflict" @change="loadAddresses">仅看冲突</el-checkbox>
                  <el-button :icon="Search" @click="loadAddresses">查询</el-button>
                  <span class="flex-grow" />
                  <span class="text-muted">最近扫描：{{ currentSubnet.last_scan_at ? formatTime(currentSubnet.last_scan_at) : '从未扫描' }}</span>
                </div>

                <el-table :data="addresses" v-loading="addrLoading" stripe border size="small"
                          style="width: 100%; margin-top: 10px"
                          :row-class-name="addrRowClass">
                  <el-table-column prop="ip" label="IP 地址" width="130">
                    <template #default="{ row }">
                      <span class="mono" :class="{ 'text-danger': row.conflict }">{{ row.ip }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="状态" width="92">
                    <template #default="{ row }">
                      <el-tag :type="statusTag(row.status)" size="small">{{ statusLabels[row.status] || row.status }}</el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column prop="mac" label="MAC 地址" width="150">
                    <template #default="{ row }"><span class="mono">{{ row.mac || '-' }}</span></template>
                  </el-table-column>
                  <el-table-column prop="hostname" label="主机名" min-width="140" show-overflow-tooltip />
                  <el-table-column prop="assigned_to" label="责任人" width="110" show-overflow-tooltip />
                  <el-table-column prop="purpose" label="用途" min-width="120" show-overflow-tooltip />
                  <el-table-column label="来源" width="86">
                    <template #default="{ row }">
                      <el-tag size="small" effect="plain" :type="row.source === 'manual' ? 'warning' : 'info'">
                        {{ row.source === 'manual' ? '手工' : '扫描' }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column label="最近在线" width="150">
                    <template #default="{ row }">{{ row.last_seen_at ? formatTime(row.last_seen_at) : '-' }}</template>
                  </el-table-column>
                  <el-table-column label="冲突说明" min-width="180" show-overflow-tooltip>
                    <template #default="{ row }">
                      <span v-if="row.conflict" class="text-danger">{{ row.conflict_reason }}</span>
                      <span v-else class="text-muted">-</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="操作" width="90" fixed="right">
                    <template #default="{ row }">
                      <el-button link type="primary" size="small" @click="openAssignDialog(row)">登记</el-button>
                      <el-button v-if="row.assigned_to || row.source === 'manual'" link type="danger" size="small"
                                 @click="releaseIp(row)">释放</el-button>
                    </template>
                  </el-table-column>
                  <template #empty><el-empty description="暂无地址记录，可点击「立即扫描」发现地址" :image-size="60" /></template>
                </el-table>

                <div class="pager">
                  <el-pagination
                    v-model:current-page="addrPage"
                    :page-size="addrPageSize"
                    :total="addrTotal"
                    layout="total, prev, pager, next"
                    background
                    @current-change="loadAddresses" />
                </div>
              </template>
              <el-empty v-else description="请选择左侧网段查看地址明细" />
            </el-card>
          </el-col>
        </el-row>
      </el-tab-pane>

      <!-- ========== VLAN 管理 ========== -->
      <el-tab-pane label="VLAN 管理" name="vlans">
        <el-card shadow="never">
          <template #header>
            <div class="card-header-flex">
              <span>VLAN 列表</span>
              <el-button type="primary" size="small" :icon="Plus" @click="openVlanDialog()">新建 VLAN</el-button>
            </div>
          </template>
          <el-table :data="vlans" v-loading="vlanLoading" stripe border size="small">
            <el-table-column prop="vlan_id" label="VLAN ID" width="100" />
            <el-table-column prop="name" label="名称" min-width="160" show-overflow-tooltip />
            <el-table-column prop="remark" label="备注" min-width="220" show-overflow-tooltip />
            <el-table-column prop="subnet_count" label="关联网段" width="100" align="center" />
            <el-table-column prop="created_at" label="创建时间" width="170">
              <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="120" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="openVlanDialog(row)">编辑</el-button>
                <el-button link type="danger" size="small" @click="removeVlan(row)">删除</el-button>
              </template>
            </el-table-column>
            <template #empty><el-empty description="尚未创建 VLAN" :image-size="60" /></template>
          </el-table>
        </el-card>
      </el-tab-pane>

      <!-- ========== 变更记录 ========== -->
      <el-tab-pane label="变更记录" name="logs">
        <el-card shadow="never">
          <template #header>
            <div class="card-header-flex">
              <span>IP 变更记录</span>
              <div>
                <el-select v-model="logSubnetId" placeholder="全部网段" clearable style="width: 200px"
                           @change="loadLogs">
                  <el-option v-for="s in subnets" :key="s.id" :label="s.name || s.cidr" :value="s.id" />
                </el-select>
              </div>
            </div>
          </template>
          <el-table :data="logs" v-loading="logLoading" stripe border size="small">
            <el-table-column label="时间" width="170">
              <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column prop="ip" label="IP 地址" width="130">
              <template #default="{ row }"><span class="mono">{{ row.ip }}</span></template>
            </el-table-column>
            <el-table-column label="动作" width="110">
              <template #default="{ row }">
                <el-tag size="small" :type="actionTag(row.action)">{{ actionLabels[row.action] || row.action }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="field" label="字段" width="110" />
            <el-table-column label="变更前" min-width="140" show-overflow-tooltip>
              <template #default="{ row }">{{ row.old_value || '-' }}</template>
            </el-table-column>
            <el-table-column label="变更后" min-width="140" show-overflow-tooltip>
              <template #default="{ row }">{{ row.new_value || '-' }}</template>
            </el-table-column>
            <el-table-column prop="operator" label="操作人" width="110" />
            <el-table-column prop="detail" label="说明" min-width="180" show-overflow-tooltip />
            <template #empty><el-empty description="暂无变更记录" :image-size="60" /></template>
          </el-table>
          <div class="pager">
            <el-pagination v-model:current-page="logPage" :page-size="logPageSize" :total="logTotal"
                           layout="total, prev, pager, next" background @current-change="loadLogs" />
          </div>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <!-- 网段弹窗 -->
    <el-dialog v-model="subnetDialog" :title="subnetForm.id ? '编辑网段' : '新建网段'" width="520px">
      <el-form :model="subnetForm" label-width="92px">
        <el-form-item label="名称" required>
          <el-input v-model="subnetForm.name" placeholder="如：办公网段" />
        </el-form-item>
        <el-form-item label="CIDR" required>
          <el-input v-model="subnetForm.cidr" placeholder="如：192.168.10.0/24" :disabled="!!subnetForm.id" />
        </el-form-item>
        <el-form-item label="网关">
          <el-input v-model="subnetForm.gateway" placeholder="如：192.168.10.1" />
        </el-form-item>
        <el-form-item label="用途">
          <el-input v-model="subnetForm.purpose" placeholder="如：办公终端" />
        </el-form-item>
        <el-form-item label="VLAN">
          <el-select v-model="subnetForm.vlan_ref" placeholder="选择 VLAN" clearable style="width: 100%">
            <el-option v-for="v in vlans" :key="v.id" :label="`VLAN ${v.vlan_id} · ${v.name}`" :value="v.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="自动扫描">
          <el-switch v-model="subnetForm.auto_scan" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="subnetForm.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="subnetDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingSubnet" @click="saveSubnet">保存</el-button>
      </template>
    </el-dialog>

    <!-- VLAN 弹窗 -->
    <el-dialog v-model="vlanDialog" :title="vlanForm.id ? '编辑 VLAN' : '新建 VLAN'" width="460px">
      <el-form :model="vlanForm" label-width="86px">
        <el-form-item label="VLAN ID" required>
          <el-input-number v-model="vlanForm.vlan_id" :min="1" :max="4094" style="width: 100%" />
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="vlanForm.name" placeholder="如：办公 VLAN" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="vlanForm.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="vlanDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingVlan" @click="saveVlan">保存</el-button>
      </template>
    </el-dialog>

    <!-- 手工登记弹窗 -->
    <el-dialog v-model="assignDialog" title="手工登记 / 分配 IP" width="480px">
      <el-form :model="assignForm" label-width="86px">
        <el-form-item label="IP 地址" required>
          <el-input v-model="assignForm.ip" placeholder="如：192.168.10.20" />
        </el-form-item>
        <el-form-item label="责任人">
          <el-input v-model="assignForm.assigned_to" placeholder="使用人 / 团队" />
        </el-form-item>
        <el-form-item label="用途">
          <el-input v-model="assignForm.purpose" placeholder="如：打印机 / 服务器" />
        </el-form-item>
        <el-form-item label="主机名">
          <el-input v-model="assignForm.hostname" placeholder="可选" />
        </el-form-item>
        <el-form-item label="MAC">
          <el-input v-model="assignForm.mac" placeholder="可选" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="assignForm.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="assignDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingAssign" @click="saveAssign">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { Plus, Refresh, Search } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../../utils/api'

const activeTab = ref('subnets')

const subnets = ref([])
const vlans = ref([])
const subnetLoading = ref(false)
const vlanLoading = ref(false)
const selectedSubnetId = ref(null)
const scanningId = ref(null)

const addresses = ref([])
const addrLoading = ref(false)
const addrStatus = ref('')
const addrKeyword = ref('')
const onlyConflict = ref(false)
const addrPage = ref(1)
const addrPageSize = ref(50)
const addrTotal = ref(0)

const conflicts = ref([])

const logs = ref([])
const logLoading = ref(false)
const logSubnetId = ref(null)
const logPage = ref(1)
const logPageSize = ref(30)
const logTotal = ref(0)

const statusLabels = {
  used: '已使用',
  free: '空闲',
  unknown: '未知',
  conflict: '冲突',
  reserved: '已登记',
}
const actionLabels = {
  assign: '手工分配',
  release: '释放',
  scan_new: '扫描新增',
  scan_update: '扫描更新',
  status_change: '状态变更',
  conflict: '冲突检测',
}

const currentSubnet = computed(() => subnets.value.find((s) => s.id === selectedSubnetId.value) || null)

const subnetDialog = ref(false)
const savingSubnet = ref(false)
const subnetForm = reactive({
  id: null, name: '', cidr: '', gateway: '', purpose: '', vlan_ref: null, remark: '', auto_scan: true,
})

const vlanDialog = ref(false)
const savingVlan = ref(false)
const vlanForm = reactive({ id: null, vlan_id: null, name: '', remark: '' })

const assignDialog = ref(false)
const savingAssign = ref(false)
const assignForm = reactive({ subnet_id: null, ip: '', assigned_to: '', purpose: '', hostname: '', mac: '', remark: '' })

function statusTag(s) {
  return { used: 'success', free: 'info', unknown: 'warning', conflict: 'danger', reserved: 'warning' }[s] || 'info'
}
function actionTag(a) {
  return { assign: 'primary', release: 'warning', scan_new: 'success', scan_update: 'info', status_change: 'warning', conflict: 'danger' }[a] || 'info'
}
function formatTime(v) {
  if (!v) return '-'
  const d = new Date(v)
  if (Number.isNaN(d.getTime())) return v
  return d.toLocaleString('zh-CN', { hour12: false })
}
function addrRowClass({ row }) {
  return row.conflict ? 'conflict-row' : ''
}

async function loadSubnets(keepSelection = true) {
  subnetLoading.value = true
  try {
    const { data } = await api.get('/ipam/subnets')
    subnets.value = data || []
    if (!keepSelection || !subnets.value.find((s) => s.id === selectedSubnetId.value)) {
      if (subnets.value.length) selectSubnet(subnets.value[0])
      else selectedSubnetId.value = null
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '获取网段失败')
  } finally {
    subnetLoading.value = false
  }
}

async function loadVlans() {
  vlanLoading.value = true
  try {
    const { data } = await api.get('/ipam/vlans')
    vlans.value = data || []
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '获取 VLAN 失败')
  } finally {
    vlanLoading.value = false
  }
}

async function loadConflicts() {
  try {
    const { data } = await api.get('/ipam/conflicts', { params: { subnet_id: selectedSubnetId.value || undefined } })
    conflicts.value = data || []
  } catch { conflicts.value = [] }
}

function selectSubnet(s) {
  selectedSubnetId.value = s.id
  addrPage.value = 1
  loadAddresses()
  loadConflicts()
}

async function loadAddresses() {
  if (!currentSubnet.value) return
  addrLoading.value = true
  try {
    const { data } = await api.get('/ipam/addresses', {
      params: {
        subnet_id: currentSubnet.value.id,
        status: addrStatus.value || undefined,
        keyword: addrKeyword.value.trim() || undefined,
        only_conflict: onlyConflict.value || undefined,
        page: addrPage.value,
        page_size: addrPageSize.value,
      },
    })
    addresses.value = data.items || []
    addrTotal.value = data.total || 0
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '获取地址列表失败')
  } finally {
    addrLoading.value = false
  }
}

async function loadLogs() {
  logLoading.value = true
  try {
    const { data } = await api.get('/ipam/changelogs', {
      params: { subnet_id: logSubnetId.value || undefined, page: logPage.value, page_size: logPageSize.value },
    })
    logs.value = data.items || []
    logTotal.value = data.total || 0
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '获取变更记录失败')
  } finally {
    logLoading.value = false
  }
}

// ---------- 网段 ----------

function openSubnetDialog(row) {
  Object.assign(subnetForm, row
    ? { id: row.id, name: row.name, cidr: row.cidr, gateway: row.gateway, purpose: row.purpose, vlan_ref: row.vlan_ref, remark: row.remark, auto_scan: row.auto_scan }
    : { id: null, name: '', cidr: '', gateway: '', purpose: '', vlan_ref: null, remark: '', auto_scan: true })
  subnetDialog.value = true
}

async function saveSubnet() {
  if (!subnetForm.cidr.trim()) { ElMessage.warning('请填写 CIDR'); return }
  savingSubnet.value = true
  try {
    if (subnetForm.id) {
      await api.put(`/ipam/subnets/${subnetForm.id}`, {
        name: subnetForm.name, gateway: subnetForm.gateway, purpose: subnetForm.purpose,
        vlan_ref: subnetForm.vlan_ref, remark: subnetForm.remark, auto_scan: subnetForm.auto_scan,
      })
    } else {
      await api.post('/ipam/subnets', {
        name: subnetForm.name, cidr: subnetForm.cidr, gateway: subnetForm.gateway,
        purpose: subnetForm.purpose, vlan_ref: subnetForm.vlan_ref,
        remark: subnetForm.remark, auto_scan: subnetForm.auto_scan,
      })
    }
    ElMessage.success('保存成功')
    subnetDialog.value = false
    await loadSubnets()
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '保存失败')
  } finally {
    savingSubnet.value = false
  }
}

async function removeSubnet(row) {
  try {
    await ElMessageBox.confirm(`确认删除网段 ${row.cidr}？其地址与变更记录将一并删除。`, '删除确认', { type: 'warning' })
  } catch { return }
  try {
    await api.delete(`/ipam/subnets/${row.id}`)
    ElMessage.success('已删除')
    if (selectedSubnetId.value === row.id) selectedSubnetId.value = null
    await loadSubnets()
    await loadConflicts()
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '删除失败')
  }
}

async function scanSubnet(row) {
  scanningId.value = row.id
  try {
    const { data } = await api.post(`/ipam/subnets/${row.id}/scan`)
    ElMessage.success(`扫描完成：已用 ${data.scan?.used ?? 0} / ${data.scan?.total ?? 0}`)
    await loadSubnets()
    if (selectedSubnetId.value === row.id) await loadAddresses()
    await loadConflicts()
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '扫描失败')
  } finally {
    scanningId.value = null
  }
}

// ---------- VLAN ----------

function openVlanDialog(row) {
  Object.assign(vlanForm, row
    ? { id: row.id, vlan_id: row.vlan_id, name: row.name, remark: row.remark }
    : { id: null, vlan_id: null, name: '', remark: '' })
  vlanDialog.value = true
}

async function saveVlan() {
  if (!vlanForm.vlan_id) { ElMessage.warning('请填写 VLAN ID'); return }
  savingVlan.value = true
  try {
    if (vlanForm.id) {
      await api.put(`/ipam/vlans/${vlanForm.id}`, {
        vlan_id: vlanForm.vlan_id, name: vlanForm.name, remark: vlanForm.remark,
      })
    } else {
      await api.post('/ipam/vlans', {
        vlan_id: vlanForm.vlan_id, name: vlanForm.name, remark: vlanForm.remark,
      })
    }
    ElMessage.success('保存成功')
    vlanDialog.value = false
    await loadVlans()
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '保存失败')
  } finally {
    savingVlan.value = false
  }
}

async function removeVlan(row) {
  try {
    await ElMessageBox.confirm(`确认删除 VLAN ${row.vlan_id}？关联网段将解除绑定。`, '删除确认', { type: 'warning' })
  } catch { return }
  try {
    await api.delete(`/ipam/vlans/${row.id}`)
    ElMessage.success('已删除')
    await loadVlans()
    await loadSubnets()
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '删除失败')
  }
}

// ---------- 地址 ----------

function openAssignDialog(row) {
  if (!currentSubnet.value) return
  Object.assign(assignForm, {
    subnet_id: currentSubnet.value.id,
    ip: row?.ip || '',
    assigned_to: row?.assigned_to || '',
    purpose: row?.purpose || '',
    hostname: row?.hostname || '',
    mac: row?.mac || '',
    remark: row?.remark || '',
  })
  assignDialog.value = true
}

async function saveAssign() {
  if (!assignForm.ip.trim()) { ElMessage.warning('请填写 IP 地址'); return }
  savingAssign.value = true
  try {
    await api.post('/ipam/addresses/assign', { ...assignForm })
    ElMessage.success('登记成功')
    assignDialog.value = false
    await loadAddresses()
    await loadSubnets()
    await loadConflicts()
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '登记失败')
  } finally {
    savingAssign.value = false
  }
}

async function releaseIp(row) {
  try {
    await ElMessageBox.confirm(`确认释放 ${row.ip} 的手工登记？`, '释放确认', { type: 'warning' })
  } catch { return }
  try {
    await api.post(`/ipam/addresses/${row.id}/release`)
    ElMessage.success('已释放')
    await loadAddresses()
    await loadSubnets()
    await loadConflicts()
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '释放失败')
  }
}

// ---------- 冲突 ----------

function jumpToConflict(c) {
  selectedSubnetId.value = c.subnet_id
  addrStatus.value = ''
  onlyConflict.value = true
  addrPage.value = 1
  loadAddresses()
  loadConflicts()
}

function focusConflict() {
  activeTab.value = 'subnets'
  onlyConflict.value = true
  addrPage.value = 1
  loadAddresses()
}

onMounted(async () => {
  await Promise.all([loadVlans(), loadSubnets()])
  await loadConflicts()
  await loadLogs()
})
</script>

<style scoped>
.conflict-banner {
  margin-bottom: 12px;
}
.conflict-title {
  font-weight: 600;
}
.conflict-list {
  margin-top: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.conflict-tag {
  cursor: pointer;
}
.card-header-flex {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.subnet-list {
  max-height: 640px;
  overflow-y: auto;
}
.subnet-item {
  padding: 10px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  margin-bottom: 10px;
  cursor: pointer;
  transition: all 0.2s;
}
.subnet-item:hover {
  border-color: var(--el-color-primary-light-5);
}
.subnet-item.active {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
.subnet-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}
.subnet-name {
  font-weight: 600;
  font-size: 14px;
}
.subnet-cidr {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin: 4px 0 8px;
}
.subnet-meta {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 6px;
}
.subnet-actions {
  margin-top: 6px;
  display: flex;
  gap: 4px;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.flex-grow {
  flex: 1;
}
.stat-row {
  margin-bottom: 4px;
}
.pager {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}
:deep(.conflict-row) {
  --el-table-tr-bg-color: rgba(245, 108, 108, 0.08);
}
:deep(.conflict-row td) {
  background: rgba(245, 108, 108, 0.08) !important;
}
@media (max-width: 768px) {
  .subnet-list { max-height: none; }
}
</style>
