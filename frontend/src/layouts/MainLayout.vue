<template>
  <el-container class="lark-layout">
    <!-- 侧边栏：极简、浅灰色背景、无边框 -->
    <el-aside width="192px" class="lark-sidebar">
      <div class="lark-logo">
        <div class="logo-box">
          <el-icon color="#fff" :size="20"><Box /></el-icon>
        </div>
        <transition name="fade">
          <h1 class="logo-text">Factory ERP</h1>
        </transition>
      </div>

      <el-scrollbar class="lark-menu-scroll">
        <el-menu
          :default-active="activeMenu"
          class="lark-menu"
          router
          background-color="var(--lark-bg-sidebar)"
          text-color="var(--lark-text-regular)"
          active-text-color="var(--lark-primary)"
        >
          <el-menu-item index="/dashboard">
            <el-icon><DataLine /></el-icon>
            <template #title><span>数据看板</span></template>
          </el-menu-item>

          <el-sub-menu index="business">
            <template #title>
              <el-icon><Management /></el-icon>
              <span>业务管理</span>
            </template>
            <el-menu-item index="/products">
              <el-icon><Goods /></el-icon>
              <template #title>产品列表</template>
            </el-menu-item>
            <el-menu-item index="/sales">
              <el-icon><List /></el-icon>
              <template #title>销售订单</template>
            </el-menu-item>
            <el-menu-item index="/shipments">
              <el-icon><Box /></el-icon>
              <template #title>销售发货单</template>
            </el-menu-item>
            <el-menu-item index="/downstream-order-reviews">
              <el-icon><ChatDotRound /></el-icon>
              <template #title>订单待审核</template>
            </el-menu-item>
            <el-menu-item index="/inventory" @click="handleUndeveloped">
              <el-icon><Search /></el-icon>
              <template #title>库存查询</template>
            </el-menu-item>
          </el-sub-menu>

          <el-sub-menu index="system">
            <template #title>
              <el-icon><Setting /></el-icon>
              <span>系统设置</span>
            </template>
            <el-menu-item index="/users">
              <el-icon><UserFilled /></el-icon>
              <template #title>人员管理</template>
            </el-menu-item>
            <el-menu-item index="/roles">
              <el-icon><Stamp /></el-icon>
              <template #title>权限管理</template>
            </el-menu-item>
            <el-menu-item index="/external-config">
              <el-icon><Link /></el-icon>
              <template #title>外部配置</template>
            </el-menu-item>
            <el-menu-item index="/logs">
              <el-icon><Document /></el-icon>
              <template #title>系统日志</template>
            </el-menu-item>
          </el-sub-menu>

        </el-menu>
      </el-scrollbar>

    </el-aside>

    <el-container class="lark-main-container">
      <!-- 顶部导航：无阴影、极简白 -->
      <el-header class="lark-header">
        <div class="lark-header-left">
          <!-- 面包屑更轻量 -->
          <el-breadcrumb separator="/">
            <el-breadcrumb-item :to="{ path: '/' }">工作台</el-breadcrumb-item>
            <el-breadcrumb-item v-if="route.meta.parent" :to="{ path: route.meta.parent.path }">
              {{ route.meta.parent.title }}
            </el-breadcrumb-item>
            <el-breadcrumb-item v-if="route.meta.title && route.path !== '/dashboard'">
              <span style="color: var(--lark-text-primary); font-weight: 600;">{{ route.meta.title }}</span>
            </el-breadcrumb-item>
          </el-breadcrumb>
        </div>

        <div class="lark-header-right">
          <div class="lark-search-box" @keydown.enter.prevent="handleSearchEnter">
             <el-icon class="search-icon"><Search /></el-icon>
             <input
               ref="searchInputRef"
               v-model.trim="searchKeyword"
               type="text"
               placeholder="搜索应用、功能或文档..."
               class="lark-search-input"
               @focus="searchFocused = true"
               @blur="onSearchBlur"
             />
             <span class="search-shortcut">{{ isMac ? '⌘K' : 'Ctrl+K' }}</span>

             <div v-if="showSearchPanel" class="search-result-panel">
               <div v-if="searchLoading" class="search-empty">搜索中...</div>
               <div v-else-if="filteredSearchItems.length === 0" class="search-empty">未找到匹配内容</div>
               <button
                 v-for="item in filteredSearchItems"
                 :key="item.id"
                 class="search-result-item"
                 @mousedown.prevent
                 @click="goToSearchItem(item)"
               >
                 <span class="result-title">{{ item.title }}</span>
                 <span class="result-meta">{{ item.meta }}</span>
               </button>
             </div>
          </div>

          <div class="lark-actions">
            <div class="lark-action-item">
               <el-badge is-dot :hidden="false">
                 <el-icon :size="20"><Bell /></el-icon>
               </el-badge>
            </div>
            <div class="lark-action-item">
               <el-icon :size="20"><QuestionFilled /></el-icon>
            </div>
          </div>

          <el-dropdown @command="handleCommand" trigger="click" class="lark-user-dropdown">
            <div class="lark-avatar-wrapper">
               <el-avatar :size="32" src="https://cube.elemecdn.com/0/88/03b0d39583f48206768a7534e55bcpng.png" />
            </div>
            <template #dropdown>
              <div class="lark-dropdown-header">
                <div class="user-info-detail">
                  <div class="user-name">{{ userStore.realName || userStore.username }}</div>
                  <div class="user-role">{{ isSuperAdmin ? '系统超级管理员' : '普通用户' }}</div>
                </div>
              </div>
              <el-dropdown-menu class="lark-dropdown-menu">
                <el-dropdown-item>
                  <el-icon><User /></el-icon>个人设置
                </el-dropdown-item>
                <el-dropdown-item>
                  <el-icon><Setting /></el-icon>偏好设置
                </el-dropdown-item>
                <el-dropdown-item divided command="logout" class="logout-item">
                  <el-icon><SwitchButton /></el-icon>退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <!-- 内容区：带灰色背景，内部组件带白色圆角 -->
      <el-main class="lark-content">
        <div class="lark-page-wrapper">
          <router-view v-slot="{ Component }">
            <transition name="fade-page" mode="out-in">
              <component :is="Component" />
            </transition>
          </router-view>
        </div>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  DataLine, User, Setting, Fold, Expand, Box, UserFilled,
  Search, Bell, SwitchButton, Stamp, Management, Goods, List, QuestionFilled,
  ChatDotRound, Monitor, Link, Document
} from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'
import { getProducts } from '@/api/products'
import { getSalesOrders } from '@/api/salesOrders'
import { getSalesShipments } from '@/api/salesShipments'
import { getUserList } from '@/api/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const isMac = /Mac|iPhone|iPad|iPod/i.test(navigator.platform)
const superAdminAliases = ['super_admin', 'superadmin', 'sys_admin', '系统超级管理员', '超级管理员']

const searchInputRef = ref(null)
const searchKeyword = ref('')
const searchFocused = ref(false)
const searchLoading = ref(false)
const remoteSearchItems = ref([])
let searchTimer = null
let searchTaskId = 0

const globalSearchItems = computed(() => {
  const routeItems = router.getRoutes()
    .filter((r) => {
      if (!r.meta?.title) return false
      if (!r.path || r.path === '/login') return false
      if (r.path.includes('/:')) return false
      return true
    })
    .map((r) => ({
      id: `route:${r.path}`,
      title: r.meta.title,
      path: r.path,
      meta: '页面',
      keywords: `${r.name || ''} ${r.meta.title || ''} ${r.path}`,
      itemType: 'route'
    }))

  return Array.from(new Map(routeItems.map((item) => [item.path, item])).values())
})

function normalizeText(text) {
  return String(text || '').toLowerCase().trim()
}

const filteredSearchItems = computed(() => {
  const q = normalizeText(searchKeyword.value)
  const baseItems = [...globalSearchItems.value, ...remoteSearchItems.value]
  if (!q) return baseItems.slice(0, 8)

  const scored = baseItems.map((item) => {
    const title = normalizeText(item.title)
    const meta = normalizeText(item.meta)
    const keywords = normalizeText(item.keywords)

    let score = 0
    if (title.startsWith(q)) score += 100
    else if (title.includes(q)) score += 70
    if (meta.includes(q)) score += 25
    if (keywords.includes(q)) score += 20

    return { item, score }
  })

  return scored
    .filter((s) => s.score > 0)
    .sort((a, b) => b.score - a.score || a.item.title.length - b.item.title.length)
    .slice(0, 8)
    .map((s) => s.item)
})

const showSearchPanel = computed(() => searchFocused.value)

function onSearchBlur() {
  setTimeout(() => {
    searchFocused.value = false
  }, 120)
}

function goToSearchItem(item) {
  if (!item?.path) return
  if (item.query) router.push({ path: item.path, query: item.query })
  else if (route.path !== item.path) router.push(item.path)
  searchKeyword.value = ''
  searchFocused.value = false
}

function handleSearchEnter() {
  if (!filteredSearchItems.value.length) {
    ElMessage.warning('未找到匹配内容')
    return
  }
  goToSearchItem(filteredSearchItems.value[0])
}

function handleGlobalShortcut(e) {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    searchFocused.value = true
    searchInputRef.value?.focus()
    searchInputRef.value?.select()
  }
}

const isSuperAdmin = computed(() => {
  const roles = (userStore.roles || []).map((item) => String(item || '').trim().toLowerCase())
  return userStore.permissions.includes('*') || roles.some((role) => superAdminAliases.includes(role))
})

function hasPermission(permissionCode) {
  if (isSuperAdmin.value) return true
  if (userStore.permissions.includes('*')) return true
  return userStore.permissions.includes(permissionCode)
}

async function fetchRemoteSearchItems(keyword) {
  const taskId = ++searchTaskId
  const q = normalizeText(keyword)
  if (!q) {
    remoteSearchItems.value = []
    return
  }

  searchLoading.value = true
  try {
    const userSearchTask = hasPermission('system:user:list')
      ? getUserList({ page: 1, page_size: 5, keyword: q })
      : Promise.resolve({ data: { list: [] } })

    const [productRes, orderRes, shipmentRes, userRes] = await Promise.allSettled([
      getProducts({ page: 1, page_size: 5, keyword: q }),
      getSalesOrders({ page: 1, page_size: 5, keyword: q }),
      getSalesShipments({ page: 1, page_size: 5, keyword: q }),
      userSearchTask
    ])

    if (taskId !== searchTaskId) return

    const products = productRes.status === 'fulfilled'
      ? (productRes.value?.data?.list || []).map((p) => ({
          id: `product:${p.id}`,
          title: `${p.product_name || '未命名产品'}`,
          meta: `产品 · ${p.product_no || '-'}${p.brand ? ` · ${p.brand}` : ''}`,
          path: '/products',
          query: { keyword: q },
          keywords: `${p.product_name || ''} ${p.product_no || ''} ${p.brand || ''}`,
          itemType: 'product'
        }))
      : []

    const orders = orderRes.status === 'fulfilled'
      ? (orderRes.value?.data?.list || []).map((o) => ({
          id: `order:${o.id}`,
          title: `${o.order_no || '订单'}`,
          meta: `销售订单 · ${o.customer_name || '未知客户'}`,
          path: o.order_no ? `/sales/${encodeURIComponent(o.order_no)}` : '/sales',
          keywords: `${o.order_no || ''} ${o.customer_name || ''}`,
          itemType: 'order'
        }))
      : []

    const shipments = shipmentRes.status === 'fulfilled'
      ? (shipmentRes.value?.data?.list || []).map((s) => ({
          id: `shipment:${s.id}`,
          title: `${s.order_no || '发货单'}`,
          meta: `销售发货单 · ${s.customer_name || '未知客户'}`,
          path: s.order_no ? `/shipments/${encodeURIComponent(s.order_no)}` : '/shipments',
          keywords: `${s.order_no || ''} ${s.customer_name || ''}`,
          itemType: 'shipment'
        }))
      : []

    const users = userRes.status === 'fulfilled'
      ? (userRes.value?.data?.list || []).map((u) => ({
          id: `user:${u.id}`,
          title: `${u.real_name || u.username || '用户'}`,
          meta: `人员管理 · ${u.username || '-'}${u.email ? ` · ${u.email}` : ''}`,
          path: '/users',
          query: { keyword: q },
          keywords: `${u.real_name || ''} ${u.username || ''} ${u.email || ''}`,
          itemType: 'user'
        }))
      : []

    remoteSearchItems.value = [...products, ...orders, ...shipments, ...users]
  } catch {
    if (taskId === searchTaskId) {
      remoteSearchItems.value = []
    }
  } finally {
    if (taskId === searchTaskId) {
      searchLoading.value = false
    }
  }
}

watch(searchKeyword, (v) => {
  clearTimeout(searchTimer)
  const keyword = normalizeText(v)
  if (!keyword) {
    remoteSearchItems.value = []
    searchLoading.value = false
    return
  }
  searchTimer = setTimeout(() => {
    fetchRemoteSearchItems(keyword)
  }, 250)
})

const activeMenu = computed(() => {
  const p = route.path
  if (p === '/customers') return '/users'
  if (p.startsWith('/sales/')) return '/sales'
  if (p.startsWith('/shipments/')) return '/shipments'
  return p
})

const handleUndeveloped = () => {
  ElMessage.warning('该功能暂未开发，敬请期待！')
  // 阻止导航，回到当前页
  router.replace(route.fullPath)
}


const handleCommand = (command) => {
  if (command === 'logout') {
    ElMessageBox.confirm('确定要退出登录吗？', '退出确认', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
      customClass: 'lark-confirm'
    }).then(() => {
      userStore.logout()
    }).catch(() => {})
  }
}

onMounted(() => {
  userStore.fetchUserInfo().catch(() => {})
  window.addEventListener('keydown', handleGlobalShortcut)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleGlobalShortcut)
  clearTimeout(searchTimer)
})
</script>

<style scoped>
.lark-layout {
  height: 100vh;
  background-color: var(--lark-bg-body);
  overflow: hidden;
}

/* 侧边栏 */
.lark-sidebar {
  background-color: var(--lark-bg-sidebar);
  border-right: 1px solid var(--lark-border-light);
  display: flex;
  flex-direction: column;
  transition: width 0.2s cubic-bezier(0.2, 0, 0, 1);
  z-index: 100;
}

.lark-logo {
  height: 60px;
  display: flex;
  align-items: center;
  padding: 0 18px;
  cursor: pointer;
  flex-shrink: 0;
}

.logo-box {
  width: 32px;
  height: 32px;
  background: linear-gradient(135deg, var(--lark-primary) 0%, #6698ff 100%);
  border-radius: var(--lark-radius);
  display: flex;
  justify-content: center;
  align-items: center;
  margin-right: 12px;
  flex-shrink: 0;
}

.logo-text {
  font-size: 18px;
  font-weight: 700;
  color: var(--lark-text-primary);
  margin: 0;
  white-space: nowrap;
}

.lark-menu-scroll {
  flex: 1;
  overflow-x: hidden;
}

/* 飞书菜单样式重写 */
.lark-menu {
  border-right: none;
  padding: 10px 8px;
}

:deep(.el-sub-menu__title) {
  height: 44px;
  line-height: 44px;
  border-radius: var(--lark-radius);
  margin-bottom: 4px;
  font-size: 14px;
}

:deep(.el-sub-menu__title:hover) {
  background-color: var(--lark-bg-hover) !important;
}

:deep(.el-menu-item) {
  height: 40px;
  line-height: 40px;
  border-radius: var(--lark-radius);
  margin-bottom: 4px;
  font-size: 14px;
  transition: all 0.2s ease;
}

:deep(.el-menu-item:hover) {
  background-color: var(--lark-bg-hover) !important;
}

:deep(.el-menu-item.is-active) {
  background-color: var(--lark-primary-light) !important;
  color: var(--lark-primary);
  font-weight: 500;
}

/* 图标调整 */
:deep(.el-menu-item .el-icon), :deep(.el-sub-menu__title .el-icon) {
  font-size: 18px;
  margin-right: 12px;
  width: 24px;
  text-align: center;
}

/* 右侧主容器 */
.lark-main-container {
  display: flex;
  flex-direction: column;
  min-width: 0; /* 解决内容撑破flex布局的问题 */
}

/* 顶部 Header */
.lark-header {
  height: 60px;
  background-color: var(--lark-bg-base);
  border-bottom: 1px solid var(--lark-border-light);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  z-index: 90;
}

.lark-header-left {
  display: flex;
  align-items: center;
}

:deep(.el-breadcrumb__item:last-child .el-breadcrumb__inner) {
  color: var(--lark-text-primary);
}

.lark-header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

/* 飞书风格搜索框 */
.lark-search-box {
  display: flex;
  align-items: center;
  position: relative;
  background-color: var(--lark-bg-hover);
  border-radius: 18px;
  padding: 0 12px;
  height: 36px;
  width: 280px;
  transition: all 0.2s;
  border: 1px solid transparent;
}

.lark-search-box:focus-within {
  background-color: var(--lark-bg-base);
  border-color: var(--lark-primary);
  box-shadow: 0 0 0 2px var(--lark-primary-light);
}

.search-icon {
  color: var(--lark-text-secondary);
  font-size: 16px;
}

.lark-search-input {
  border: none;
  background: transparent;
  outline: none;
  flex: 1;
  padding: 0 8px;
  font-size: 14px;
  color: var(--lark-text-primary);
}

.lark-search-input::placeholder {
  color: var(--lark-text-secondary);
}

.search-shortcut {
  font-size: 12px;
  color: var(--lark-text-secondary);
  background-color: var(--lark-bg-base);
  padding: 2px 6px;
  border-radius: 4px;
  border: 1px solid var(--lark-border-light);
}

.search-result-panel {
  position: absolute;
  top: 42px;
  left: 0;
  right: 0;
  background: #fff;
  border: 1px solid var(--lark-border-light);
  border-radius: 12px;
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.08);
  padding: 6px;
  z-index: 200;
  max-height: 300px;
  overflow-y: auto;
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.search-result-panel::-webkit-scrollbar {
  display: none;
}

.search-empty {
  font-size: 13px;
  color: var(--lark-text-secondary);
  padding: 10px 12px;
}

.search-result-item {
  width: 100%;
  border: none;
  background: transparent;
  border-radius: 8px;
  padding: 10px 12px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
}

.search-result-item:hover {
  background-color: var(--lark-bg-hover);
}

.result-title {
  font-size: 14px;
  color: var(--lark-text-primary);
}

.result-meta {
  font-size: 12px;
  color: var(--lark-text-secondary);
}

/* 操作图标 */
.lark-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.lark-action-item {
  width: 36px;
  height: 36px;
  border-radius: var(--lark-radius);
  display: flex;
  justify-content: center;
  align-items: center;
  cursor: pointer;
  color: var(--lark-text-regular);
  transition: background-color 0.2s;
}

.lark-action-item:hover {
  background-color: var(--lark-bg-hover);
  color: var(--lark-text-primary);
}

/* 用户头像下拉 */
.lark-user-dropdown {
  cursor: pointer;
}

.lark-avatar-wrapper {
  padding: 2px;
  border-radius: 50%;
  border: 1px solid transparent;
  transition: border-color 0.2s;
}

.lark-avatar-wrapper:hover {
  border-color: var(--lark-primary);
}

.lark-dropdown-header {
  padding: 16px 20px;
  border-bottom: 1px solid var(--lark-border-light);
  display: flex;
  align-items: center;
  gap: 12px;
}

.user-info-detail {
  display: flex;
  flex-direction: column;
}

.user-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--lark-text-primary);
  margin-bottom: 2px;
}

.user-role {
  font-size: 12px;
  color: var(--lark-text-secondary);
}

.lark-dropdown-menu {
  padding: 8px !important;
  min-width: 200px;
}

:deep(.lark-dropdown-menu .el-dropdown-menu__item) {
  border-radius: var(--lark-radius-sm);
  margin-bottom: 2px;
  padding: 8px 12px;
}

:deep(.lark-dropdown-menu .el-dropdown-menu__item:hover) {
  background-color: var(--lark-bg-hover);
  color: var(--lark-text-primary);
}

.logout-item {
  color: #f54a45 !important;
}

.logout-item:hover {
  background-color: #fef0f0 !important;
}

/* 主内容区域 */
.lark-content {
  padding: 20px 24px;
  background-color: var(--lark-bg-body);
  position: relative;
  overflow-y: auto;
}

.lark-page-wrapper {
  min-height: calc(100vh - 100px);
  display: flex;
  flex-direction: column;
}

/* 过渡动画 */
.fade-page-enter-active,
.fade-page-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.fade-page-enter-from {
  opacity: 0;
  transform: translateY(10px);
}

.fade-page-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}
</style>
