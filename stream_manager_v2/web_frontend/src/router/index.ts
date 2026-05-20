import { createRouter, createWebHistory } from 'vue-router'
import DashboardView from '@/views/DashboardView.vue'
import CameraDetailView from '@/views/CameraDetailView.vue'
import ViolationsView from '@/views/ViolationsView.vue'
import TestView from '@/views/TestView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'dashboard',
      component: DashboardView,
      meta: { title: '监控大屏' }
    },
    {
      path: '/camera/:id',
      name: 'camera-detail',
      component: CameraDetailView,
      meta: { title: '摄像头详情' }
    },
    {
      path: '/violations',
      name: 'violations',
      component: ViolationsView,
      meta: { title: '违规记录' }
    },
    {
      path: '/test',
      name: 'test',
      component: TestView,
      meta: { title: '连接测试' }
    }
  ]
})

// 页面标题
router.beforeEach((to, from, next) => {
  document.title = `${to.meta.title || '监控系统'} - Stream Manager V2`
  next()
})

export default router
