import { createRouter, createWebHistory } from 'vue-router'
import MainLayout from '@/layouts/MainLayout.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: MainLayout,
      children: [
        {
          path: '',
          name: 'Dashboard',
          component: () => import('@/views/DashboardView.vue'),
          meta: { title: '监控面板' }
        },
        {
          path: '/dashboard',
          redirect: '/'
        },
        {
          path: 'streams',
          name: 'Streams',
          component: () => import('@/views/StreamsView.vue'),
          meta: { title: '视频流管理' }
        },
        {
          path: 'streams/:id',
          name: 'StreamDetail',
          component: () => import('@/views/StreamDetailView.vue'),
          meta: { title: '视频流详情' }
        },
        {
          path: 'violations',
          name: 'Violations',
          component: () => import('@/views/ViolationsView.vue'),
          meta: { title: '违规记录' }
        },
        {
          path: 'analytics',
          name: 'Analytics',
          component: () => import('@/views/AnalyticsView.vue'),
          meta: { title: '数据分析' }
        },
        {
          path: 'reports',
          name: 'Reports',
          component: () => import('@/views/ReportsView.vue'),
          meta: { title: '日报系统' }
        },
        {
          path: 'vehicle-wash',
          name: 'VehicleWash',
          component: () => import('@/views/VehicleWashView.vue'),
          meta: { title: '车辆清洗检测' }
        },
        {
          path: 'settings',
          name: 'Settings',
          component: () => import('@/views/SettingsView.vue'),
          meta: { title: '系统设置' }
        }
      ]
    }
  ]
})

router.beforeEach((to, from, next) => {
  document.title = `${to.meta.title || 'Stream V3'} - 智能监控系统`
  next()
})

export default router
