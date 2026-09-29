<template>
  <div class="page-container">
    <h2 class="page-title">AI 分析 Agent</h2>

    <el-card shadow="never">
      <div class="toolbar">
        <span class="hint">每个 Agent 是一个独立的人设（系统提示词）+ 大模型供应商配置。告警分析时可选定 Agent。</span>
        <el-button type="primary" :icon="Plus" @click="openCreate">新建 Agent</el-button>
      </div>

      <el-table :data="store.list" v-loading="loading" size="small" stripe style="margin-top:12px">
        <el-table-column prop="name" label="名称" min-width="120" />
        <el-table-column label="供应商 / 模型" min-width="200">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ row.provider }}</el-tag>
            <span class="model-name">{{ row.model || '默认模型' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="温度" width="70" align="center">
          <template #default="{ row }">{{ row.temperature }}</template>
        </el-table-column>
        <el-table-column label="人设预览" min-width="260" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="prompt-text">{{ row.system_prompt || '（未设置，使用默认 SRE 提示词）' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="默认" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.is_default" type="success" size="small">默认</el-tag>
            <el-button v-else link size="small" type="primary" @click="setDefault(row)">设为默认</el-button>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="170" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
            <el-popconfirm title="确认删除该 Agent？" @confirm="remove(row)">
              <template #reference>
                <el-button link type="danger" size="small">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="尚未配置 Agent。点击右上角「新建 Agent」开始。" />
        </template>
      </el-table>
    </el-card>

    <!-- 新建/编辑弹窗 -->
    <el-dialog v-model="dialogOpen" :title="editing ? '编辑 Agent' : '新建 Agent'"
                width="560px" :close-on-click-modal="false">
      <el-form :model="form" label-width="90px" ref="formRef">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" maxlength="64" show-word-limit />
        </el-form-item>
        <el-form-item label="供应商" required>
          <el-select v-model="form.provider" placeholder="选择大模型供应商" @change="onProviderChange">
            <el-option v-for="p in store.providers" :key="p.provider"
                       :label="`${p.label}（${p.provider}）`" :value="p.provider" />
          </el-select>
        </el-form-item>
        <el-form-item label="模型">
          <el-input v-model="form.model" placeholder="留空使用供应商默认模型" />
        </el-form-item>
        <el-form-item label="温度">
          <el-input-number v-model="form.temperature" :min="0" :max="2" :step="0.1" />
        </el-form-item>
        <el-form-item label="设为默认">
          <el-switch v-model="form.is_default" />
        </el-form-item>
        <el-form-item label="人设 (Prompt)">
          <el-input v-model="form.system_prompt" type="textarea" :rows="8"
                    placeholder="角色定位、分析风格、关注重点、输出格式等。例如：&#10;你是一名数据库 SRE，专注于 MySQL 慢查询与复制延迟分析，输出结论时优先给出复现步骤与影响范围评估。" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogOpen = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useAgentStore } from '../../stores/agent'

const store = useAgentStore()
const loading = ref(false)
const dialogOpen = ref(false)
const editing = ref(null)
const saving = ref(false)
const formRef = ref(null)

const form = reactive({
  name: '',
  provider: '',
  model: '',
  temperature: 0.2,
  is_default: false,
  system_prompt: '',
})

function resetForm() {
  form.name = ''
  form.provider = ''
  form.model = ''
  form.temperature = 0.2
  form.is_default = false
  form.system_prompt = ''
}

function openCreate() {
  resetForm()
  editing.value = null
  dialogOpen.value = true
}

function openEdit(row) {
  Object.assign(form, row)
  editing.value = row
  dialogOpen.value = true
}

function onProviderChange() {
  // 切换供应商时自动填入默认模型
  const meta = store.providers.find(p => p.provider === form.provider)
  if (meta && !form.model) form.model = meta.default_model
}

async function save() {
  if (!form.name || !form.provider) {
    ElMessage.warning('请填写名称与供应商')
    return
  }
  saving.value = true
  try {
    if (editing.value) {
      await store.update(editing.value.id, form)
    } else {
      await store.create(form)
    }
    ElMessage.success('保存成功')
    dialogOpen.value = false
  } finally {
    saving.value = false
  }
}

async function remove(row) {
  await store.remove(row.id)
  ElMessage.success('已删除')
}

async function setDefault(row) {
  await store.setDefault(row.id)
  ElMessage.success(`已将「${row.name}」设为默认`)
}

onMounted(async () => {
  loading.value = true
  try {
    await store.load()
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}
.hint {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.model-name {
  margin-left: 6px;
  font-family: ui-monospace, monospace;
  font-size: 12px;
  color: var(--el-text-color-regular);
}
.prompt-text {
  color: var(--el-text-color-regular);
  font-size: 12px;
}
</style>