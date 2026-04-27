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
        meta: { title: '组织架构', tab: 'employees' }
      },
      {
        path: 'customers',
        name: 'Customers',
        component: () => import('@/views/system/Users.vue'),
        meta: { title: '下游客户', tab: 'customers' }
      },
      {
        path: 'wechat-rooms',
        name: 'WechatRooms',
        component: () => import('@/views/system/Users.vue'),
        meta: { title: '企微群聊', tab: 'wechat-rooms' }
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
        path: 'system-center',
        name: 'SystemCenter',
        component: () => import('@/views/system/SystemCenter.vue'),
        meta: { title: '系统消息', tab: 'messages' }
      },
      {
        path: 'system-messages',
        redirect: '/system-center'
      },
      {
        path: 'system-activities',
        redirect: '/system-center'
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
        meta: { title: '销售订单' }
      },
      {
        path: 'products',
        name: 'Products',
        component: () => import('@/views/business/Products.vue'),
        meta: { title: '产品列表' }
      },
      {
        path: 'sales',
        name: 'SalesOrders',
        component: () => import('@/views/business/SalesOrders.vue'),
        meta: { title: '销售订单' }
      },
      {
        path: 'sales/:orderNo',
        name: 'SalesOrderDetail',
        component: () => import('@/views/business/SalesOrderDetail.vue'),
        meta: { title: '订单详情', parent: { title: '销售订单', path: '/sales' } }
      },
      {
        path: 'shipments',
        name: 'SalesShipments',
        component: () => import('@/views/business/SalesShipments.vue'),
        meta: { title: '销售发货单' }
      },
      {
        path: 'shipments/:orderNo',
        name: 'ShipmentDetail',
        component: () => import('@/views/business/ShipmentDetail.vue'),
        meta: { title: '发货单详情', parent: { title: '销售发货单', path: '/shipments' } }
      },
      {
        path: 'inventory',
        name: 'Inventory',
        component: () => import('@/views/business/Inventory.vue'),
        meta: { title: '库存查询' }
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
