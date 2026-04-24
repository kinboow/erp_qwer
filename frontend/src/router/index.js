import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '@/stores/user'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    redirect: '/dashboard',
    meta: { requiresAuth: true },
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/Dashboard.vue'),
        meta: { title: '首页' }
      },
      {
        path: 'users',
        name: 'Users',
        component: () => import('@/views/system/Users.vue'),
        meta: { title: '用户管理' }
      },
      {
        path: 'roles',
        name: 'Roles',
        component: () => import('@/views/system/Roles.vue'),
        meta: { title: '权限管理' }
      },
      {
        path: 'logs',
        name: 'Logs',
        component: () => import('@/views/system/Logs.vue'),
        meta: { title: '系统日志' }
      },
      {
        path: 'external-config',
        name: 'ExternalConfig',
        component: () => import('@/views/system/ExternalConfig.vue'),
        meta: { title: '外部服务配置' }
      },
      {
        path: 'downstream-order-reviews',
        name: 'DownstreamOrderReviews',
        component: () => import('@/views/business/DownstreamOrderReviews.vue'),
        meta: { title: '订单待审核' }
      },
      {
        path: 'sales',
        name: 'SalesOrders',
        component: () => import('@/views/business/SalesOrders.vue'),
        meta: { title: '销售订单' }
      },
      {
        path: 'wechat-listeners/:instanceId',
        name: 'WechatRoomListeners',
        component: () => import('@/views/wechat/RoomListeners.vue'),
        meta: { title: '群聊监听配置' }
      },
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 路由守卫
router.beforeEach((to, from, next) => {
  const userStore = useUserStore()

  if (to.meta.requiresAuth && !userStore.isLoggedIn) {
    next('/login')
  } else if (to.path === '/login' && userStore.isLoggedIn) {
    next('/')
  } else {
    next()
  }
})

export default router
