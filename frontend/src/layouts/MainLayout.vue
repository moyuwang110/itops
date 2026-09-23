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
              <el-avatar :size="28" class="user-avatar">{{ (auth.username || 'A').slice(0, 1).toUpperCase() }}</el-avatar>
              <span class="user-name">{{ auth.username || 'admin' }}</span>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="logout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { useAuthStore } from '../stores/auth'
import { useThemeStore } from '../stores/theme'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const theme = useThemeStore()

const collapsed = ref(false)
const drawerOpen = ref(false)
const isMobile = ref(window.innerWidth <= 768)

const menus = [
  { title: '总览仪表盘', icon: 'Odometer', path: '/dashboard' },
  {
    title: '告警中心', icon: 'Bell',
    children: [
      { title: '告警列表', icon: 'Bell', path: '/alerts' },
      { title: '分析报告', icon: 'Document', path: '/reports' },
    ],
  },
  { title: '监控数据', icon: 'Monitor', path: '/monitoring' },
  { title: '日志查询', icon: 'Tickets', path: '/logs' },
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
  if (command === 'logout') {
    try {
      await ElMessageBox.confirm('确认退出登录？', '提示', { type: 'warning' })
    } catch {
      return
    }
    await auth.logout()
    router.replace({ name: 'login' })
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
