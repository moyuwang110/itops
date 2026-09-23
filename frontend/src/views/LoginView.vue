<template>
  <div class="login-page">
    <div class="login-card">
      <div class="brand">
        <el-icon :size="34" color="var(--el-color-primary)"><Cpu /></el-icon>
        <h1>ITOPS 智能运维分析平台</h1>
        <p class="subtitle">Zabbix 告警 · AI 根因分析 · 日志关联 · 通知推送</p>
      </div>
      <el-form ref="formRef" :model="form" :rules="rules" @keyup.enter="submit" size="large">
        <el-form-item prop="username">
          <el-input v-model="form.username" placeholder="管理员账号" :prefix-icon="User" />
        </el-form-item>
        <el-form-item prop="password">
          <el-input v-model="form.password" type="password" show-password
                    placeholder="密码" :prefix-icon="Lock" />
        </el-form-item>
        <el-button type="primary" class="login-btn" :loading="loading" @click="submit">
          登 录
        </el-button>
      </el-form>
      <p class="tip">默认单管理员模式，首次部署后请及时修改密码</p>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Lock, User } from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const formRef = ref()
const loading = ref(false)

const form = reactive({ username: 'admin', password: '' })
const rules = {
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function submit() {
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  loading.value = true
  try {
    await auth.login(form)
    ElMessage.success('登录成功')
    router.replace(route.query.redirect || '/dashboard')
  } catch (e) {
    // 拦截器已提示错误
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  background:
    radial-gradient(1200px 600px at 20% -10%, var(--el-color-primary-light-8), transparent),
    radial-gradient(1000px 500px at 110% 110%, var(--el-color-primary-light-7), transparent),
    var(--el-bg-color-page);
}

.login-card {
  width: 100%;
  max-width: 400px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  padding: 34px 30px 24px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.08);
}

.brand {
  text-align: center;
  margin-bottom: 24px;
}

.brand h1 {
  font-size: 20px;
  margin: 12px 0 6px;
}

.subtitle {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin: 0;
}

.login-btn {
  width: 100%;
}

.tip {
  text-align: center;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  margin: 16px 0 0;
}
</style>
