<template>
  <el-container class="layout-root">
    <!-- 桌面侧边栏 -->
    <el-aside v-if="!isMobile" :width="collapsed ? 'var(--itops-sidebar-collapsed)' : 'var(--itops-sidebar-w)'"
              class="sidebar" :class="{ collapsed }">
      <div class="logo">
        <el-icon :size="22"><Cpu /></el-icon>
        <span v-show="!collapsed" class="logo-text">ITOPS 运维分析</span>
      </div>
      <el-menu :default-active="activeMenu" :collapse="collapsed" :collapse-transition="false"
               router class="side-menu" background-color="transparent">
        <template v-for="item in menus" :key="item.title">
          <el-sub-menu v-if="item.children" :index="item.title">
            <template #title>
              <el-icon><component :is="item.icon" /></el-icon>
              <span>{{ item.title }}</span>
            </template>
            <el-menu-item v-for="c in item.children" :key="c.path" :index="c.path">
              <el-icon><component :is="c.icon || item.icon" /></el-icon>
              <span>{{ c.title }}</span>
            </el-menu-item>
          </el-sub-menu>
          <el-menu-item v-else :index="item.path">
            <el-icon><component :is="item.icon" /></el-icon>
            <span>{{ item.title }}</span>
          </el-menu-item>
        </template>
      </el-menu>
    </el-aside>

    <!-- 移动端抽屉 -->
    <el-drawer v-model="drawerOpen" direction="ltr" size="240px" :with-header="false">
      <div class="logo dark-on-drawer">
        <el-icon :size="22"><Cpu /></el-icon>
        <span class="logo-text">ITOPS 运维分析</span>
      </div>
      <el-menu :default-active="activeMenu" router @select="drawerOpen = false" class="side-menu">
        <template v-for="item in menus" :key="item.title">
          <el-sub-menu v-if="item.children" :index="item.title">
            <template #title>
              <el-icon><component :is="item.icon" /></el-icon>
              <span>{{ item.title }}</span>
            </template>
            <el-menu-item v-for="c in item.children" :key="c.path" :index="c.path">
              <el-icon><component :is="c.icon || item.icon" /></el-icon>
              <span>{{ c.title }}</span>
            </el-menu-item>
          </el-sub-menu>
          <el-menu-item v-else :index="item.path">
            <el-icon><component :is="item.icon" /></el-icon>
            <span>{{ item.title }}</span>
          </el-menu-item>
        </template>
      </el-menu>
    </el-drawer>

    <el-container>
      <el-header class="header">
        <div class="header-left">
          <el-icon class="collapse-btn" :size="20" @click="toggleSidebar">
            <Fold v-if="!isMobile && !collapsed" />
            <Expand v-else />
          </el-icon>
          <span class="page-name">{{ pageTitle }}</span>
        </div>
        <div class="header-right">
          <el-tooltip :content="themeLabel" placement="bottom">
            <el-icon class="header-action" :size="18" @click="cycleTheme">
              <component :is="themeIcon" />
            </el-icon>
          </el-tooltip>
          <el-dropdown @command="onUser">
            <span class="user-area">
              <el-avatar :size="28" class="user-avatar" :src="auth.avatar || undefined">
                {{ (auth.username || 'A').slice(0, 1).toUpperCase() }}
              </el-avatar>
              <span class="user-name">{{ auth.username || 'admin' }}</span>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="profile">个人设置</el-dropdown-item>
                <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>

    <!-- 个人设置弹窗 -->
    <el-dialog v-model="profileOpen" title="个人设置" width="460px" :close-on-click-modal="false"
               @close="profileTab = 'info'">
      <el-tabs v-model="profileTab">
        <el-tab-pane label="基本信息" name="info">
          <el-form :model="profileForm" label-width="80px">
            <el-form-item label="用户名">
              <el-input v-model="profileForm.username" maxlength="64" show-word-limit />
            </el-form-item>
            <el-form-item label="头像">
              <div class="avatar-row">
                <el-avatar :size="56" :src="profileForm.avatar" class="profile-avatar">
                  {{ (profileForm.username || 'A').slice(0, 1).toUpperCase() }}
                </el-avatar>
                <div class="avatar-actions">
                  <el-input v-model="profileForm.avatar" placeholder="头像图片 URL，留空使用首字母" clearable />
                  <span class="avatar-tip">支持 http(s) 图片链接或 base64（data:image/...）</span>
                </div>
              </div>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="savingProfile" @click="saveProfile">保存</el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>
        <el-tab-pane label="修改密码" name="password">
          <el-form :model="pwdForm" label-width="90px">
            <el-form-item label="原密码">
              <el-input v-model="pwdForm.oldPassword" type="password" show-password />
            </el-form-item>
            <el-form-item label="新密码">
              <el-input v-model="pwdForm.newPassword" type="password" show-password placeholder="至少 6 位" />
            </el-form-item>
            <el-form-item label="确认新密码">
              <el-input v-model="pwdForm.confirmPassword" type="password" show-password />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="changingPwd" @click="savePassword">确认修改</el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>
      </el-tabs>
    </el-dialog>
  </el-container>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '../stores/auth'
import { useThemeStore } from '../stores/theme'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const theme = useThemeStore()

const collapsed = ref(false)
const drawerOpen = ref(false)
const isMobile = ref(window.innerWidth <= 768)

// 个人设置弹窗状态
const profileOpen = ref(false)
const profileTab = ref('info')
const savingProfile = ref(false)
const changingPwd = ref(false)
const profileForm = reactive({ username: '', avatar: '' })
const pwdForm = reactive({ oldPassword: '', newPassword: '', confirmPassword: '' })

const menus = [
  { title: '总览仪表盘', icon: 'Odometer', path: '/dashboard' },
  { title: '工作台', icon: 'Platform', path: '/workbench' },
  {
    title: '告警中心', icon: 'Bell',
    children: [
      { title: '告警列表', icon: 'Bell', path: '/alerts' },
      { title: '已恢复告警', icon: 'CircleCheck', path: '/alerts/resolved' },
      { title: '分析报告', icon: 'Document', path: '/reports' },
    ],
  },
  { title: '监控数据', icon: 'Monitor',
    children: [
      { title: '主机与监控项', icon: 'Monitor', path: '/monitoring' },
      { title: '未恢复问题', icon: 'Warning', path: '/monitoring/problems' },
    ],
  },
  { title: '日志查询', icon: 'Tickets', path: '/logs' },
  { title: 'AI Agent', icon: 'MagicStick', path: '/agents' },
  {
    title: '集成配置', icon: 'Setting',
    children: [
      { title: 'Zabbix', icon: 'Connection', path: '/settings/zabbix' },
      { title: '大模型', icon: 'ChatDotRound', path: '/settings/llm' },
      { title: '日志平台', icon: 'Files', path: '/settings/logs' },
      { title: '通知渠道', icon: 'Promotion', path: '/settings/notify' },
      { title: '分析参数', icon: 'Tools', path: '/settings/system' },
    ],
  },
]

const activeMenu = computed(() => {
  if (route.path.startsWith('/alerts/resolved')) return '/alerts/resolved'
  if (route.path.startsWith('/alerts')) return '/alerts'
  if (route.path.startsWith('/reports')) return '/reports'
  if (route.path.startsWith('/settings')) {
    const tab = route.params.tab || 'zabbix'
    return `/settings/${tab}`
  }
  return route.path
})

const pageTitle = computed(() => route.meta.title || 'ITOPS')

const themeIcon = computed(() => theme.mode === 'dark' ? 'Moon' : theme.mode === 'light' ? 'Sunny' : 'Monitor')
const themeLabel = computed(() => ({ system: '跟随系统（点击切浅色）', light: '浅色（点击切深色）', dark: '深色（点击切跟随系统）' }[theme.mode]))

function cycleTheme() {
  const order = ['system', 'light', 'dark']
  theme.setMode(order[(order.indexOf(theme.mode) + 1) % order.length])
}

function toggleSidebar() {
  if (isMobile.value) drawerOpen.value = !drawerOpen.value
  else collapsed.value = !collapsed.value
}

function onResize() {
  isMobile.value = window.innerWidth <= 768
  if (!isMobile.value) drawerOpen.value = false
}
onMounted(() => window.addEventListener('resize', onResize))
onBeforeUnmount(() => window.removeEventListener('resize', onResize))

async function onUser(command) {
  if (command === 'profile') {
    openProfile()
  } else if (command === 'logout') {
    try {
      await ElMessageBox.confirm('确认退出登录？', '提示', { type: 'warning' })
    } catch {
      return
    }
    await auth.logout()
    router.replace({ name: 'login' })
  }
}

// 打开个人设置弹窗，从 /auth/me 拉取最新资料回填
async function openProfile() {
  try {
    const me = await auth.fetchProfile()
    profileForm.username = me.username || ''
    profileForm.avatar = me.avatar || ''
  } catch {
    // 拉取失败时用本地缓存兜底
    profileForm.username = auth.username || ''
    profileForm.avatar = auth.avatar || ''
  }
  profileOpen.value = true
}

async function saveProfile() {
  if (!profileForm.username.trim()) {
    ElMessage.warning('用户名不能为空')
    return
  }
  savingProfile.value = true
  try {
    const payload = {
      username: profileForm.username.trim(),
      avatar: profileForm.avatar.trim() || null,
    }
    await auth.updateProfile(payload)
    ElMessage.success('资料已更新')
    profileOpen.value = false
  } catch (e) {
    // 拦截器已提示错误
  } finally {
    savingProfile.value = false
  }
}

async function savePassword() {
  if (!pwdForm.oldPassword) {
    ElMessage.warning('请输入原密码')
    return
  }
  if (!pwdForm.newPassword || pwdForm.newPassword.length < 6) {
    ElMessage.warning('新密码至少 6 位')
    return
  }
  if (pwdForm.newPassword !== pwdForm.confirmPassword) {
    ElMessage.warning('两次输入的新密码不一致')
    return
  }
  changingPwd.value = true
  try {
    await auth.changePassword(pwdForm.oldPassword, pwdForm.newPassword)
    ElMessage.success('密码已修改，请重新登录')
    pwdForm.oldPassword = ''
    pwdForm.newPassword = ''
    pwdForm.confirmPassword = ''
    profileOpen.value = false
    // 密码修改后 token 仍有效，无需强制登出；如策略要求可改为 auth.logout()
  } catch (e) {
    // 拦截器已提示错误
  } finally {
    changingPwd.value = false
  }
}
</script>

<style scoped>
.layout-root {
  height: 100vh;
}

.sidebar {
  background: var(--el-bg-color);
  border-right: 1px solid var(--el-border-color-lighter);
  transition: width 0.2s;
  overflow: hidden;
}

.side-menu {
  border-right: none;
  background: transparent;
}

.logo {
  height: var(--itops-header-h);
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 16px;
  font-weight: 700;
  color: var(--el-color-primary);
  white-space: nowrap;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.header {
  height: var(--itops-header-h);
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color-lighter);
  padding: 0 16px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.collapse-btn {
  cursor: pointer;
  color: var(--el-text-color-regular);
}

.page-name {
  font-size: 15px;
  font-weight: 600;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 18px;
}

.header-action {
  cursor: pointer;
  color: var(--el-text-color-regular);
}

.user-area {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  outline: none;
}

.user-avatar {
  background: var(--el-color-primary);
  color: #fff;
}

.user-name {
  font-size: 13px;
}

.avatar-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}
.avatar-actions {
  flex: 1;
}
.avatar-tip {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}
.profile-avatar {
  background: var(--el-color-primary);
  color: #fff;
  flex-shrink: 0;
}

.main-content {
  background: var(--el-bg-color-page);
  padding: 0;
  overflow-y: auto;
}

@media (max-width: 768px) {
  .user-name { display: none; }
  .page-name { font-size: 14px; }
}
</style>
