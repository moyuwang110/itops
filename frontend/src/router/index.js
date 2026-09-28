import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes = [
  { path: '/login', name: 'login', component: () => import('../views/LoginView.vue'), meta: { public: true } },
  {
    path: '/',
    component: () => import('../layouts/MainLayout.vue'),
    redirect: '/dashboard',
    children: [
      { path: 'dashboard', name: 'dashboard', component: () => import('../views/DashboardView.vue'), meta: { title: '总览仪表盘', icon: 'Odometer' } },
      {
        path: 'alerts',
        name: 'alerts',
        component: () => import('../views/alerts/AlertListView.vue'),
        meta: { title: '告警列表', group: '告警中心', icon: 'Bell' },
      },
      {
        path: 'alerts/:id',
        name: 'alert-detail',
        component: () => import('../views/alerts/AlertDetailView.vue'),
        meta: { title: '告警分析工作台', group: '告警中心', icon: 'Bell', hidden: true },
      },
      {
        path: 'reports',
        name: 'reports',
        component: () => import('../views/reports/ReportListView.vue'),
        meta: { title: '分析报告', group: '告警中心', icon: 'Document' },
      },
      {
        path: 'reports/:id',
        name: 'report-detail',
        component: () => import('../views/reports/ReportDetailView.vue'),
        meta: { title: '报告详情', group: '告警中心', icon: 'Document', hidden: true },
      },
      { path: 'monitoring', name: 'monitoring', component: () => import('../views/monitoring/MonitoringView.vue'), meta: { title: '主机与监控项', icon: 'Monitor' } },
      { path: 'monitoring/problems', name: 'monitoring-problems', component: () => import('../views/monitoring/ProblemsView.vue'), meta: { title: '未恢复问题', icon: 'Warning' } },
      { path: 'logs', name: 'logs', component: () => import('../views/logs/LogQueryView.vue'), meta: { title: '日志查询', icon: 'Tickets' } },
      {
        path: 'settings/:tab?',
        name: 'settings',
        component: () => import('../views/settings/SettingsView.vue'),
        meta: {
          title: '集成配置', icon: 'Setting',
          children: [
            { path: 'zabbix', title: 'Zabbix' },
            { path: 'llm', title: '大模型' },
            { path: 'logs', title: '日志平台' },
            { path: 'notify', title: '通知渠道' },
            { path: 'system', title: '分析参数' },
          ],
        },
      },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  // token 由 httpOnly Cookie 管理，前端用 username 作为已登录的快速判断
  // （真正的鉴权由后端 Cookie 校验，401 时响应拦截器会跳转登录）
  if (!to.meta.public && !auth.username) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.name === 'login' && auth.username) {
    return { name: 'dashboard' }
  }
  return true
})

export default router
