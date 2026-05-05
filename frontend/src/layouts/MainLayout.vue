<template>
  <el-container class="lark-layout">
    <!-- 侧边栏：极简、浅灰色背景、无边框 -->
    <el-aside width="192px" class="lark-sidebar">
      <div class="lark-logo">
        <img src="/logo.png" alt="logo" class="logo-img" />
        <transition name="fade">
          <h1 class="logo-text">协途AI</h1>
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

          <el-sub-menu index="products">
            <template #title>
              <el-icon><Goods /></el-icon>
              <span>商品管理</span>
            </template>
            <el-menu-item index="/products">
              <el-icon><Goods /></el-icon>
              <template #title>产品列表</template>
            </el-menu-item>
            <el-menu-item index="/products-current-year">
              <el-icon><Star /></el-icon>
              <template #title>本年产品库</template>
            </el-menu-item>
            <el-menu-item index="/inventory">
              <el-icon><Search /></el-icon>
              <template #title>库存查询</template>
            </el-menu-item>
          </el-sub-menu>

          <el-sub-menu index="orders">
            <template #title>
              <el-icon><List /></el-icon>
              <span>订单管理</span>
            </template>
            <el-menu-item index="/sales">
              <el-icon><List /></el-icon>
              <template #title>销售订单</template>
            </el-menu-item>
            <el-menu-item index="/shipments">
              <el-icon><Box /></el-icon>
              <template #title>销售发货单</template>
            </el-menu-item>
            <el-menu-item index="/unshipped-report">
              <el-icon><Tickets /></el-icon>
              <template #title>待发货报表</template>
            </el-menu-item>
          </el-sub-menu>

          <el-sub-menu index="review">
            <template #title>
              <el-icon><DocumentChecked /></el-icon>
              <span>审核管理</span>
            </template>
            <el-menu-item index="/downstream-order-reviews">
              <el-icon><ChatDotRound /></el-icon>
              <template #title>订单审核</template>
            </el-menu-item>
            <el-menu-item index="/approval-list">
              <el-icon><DocumentChecked /></el-icon>
              <template #title>审核列表</template>
            </el-menu-item>
          </el-sub-menu>

          <el-sub-menu index="system">
            <template #title>
              <el-icon><Setting /></el-icon>
              <span>系统设置</span>
            </template>
            <el-menu-item index="/users">
              <el-icon><UserFilled /></el-icon>
              <template #title>组织架构</template>
            </el-menu-item>
            <el-menu-item index="/roles">
              <el-icon><Stamp /></el-icon>
              <template #title>权限管理</template>
            </el-menu-item>
            <el-menu-item index="/config-wechat">
              <el-icon><Link /></el-icon>
              <template #title>外部配置</template>
            </el-menu-item>
            <el-menu-item index="/logs">
              <el-icon><Document /></el-icon>
              <template #title>系统日志</template>
            </el-menu-item>
            <el-menu-item index="/system-center">
              <el-icon><Bell /></el-icon>
              <template #title>消息中心</template>
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
            <el-popover
              placement="bottom-end"
              :width="380"
              trigger="hover"
              :show-after="150"
              :hide-after="100"
              @show="onMsgPopoverShow"
            >
              <template #reference>
                <div class="lark-action-item" style="cursor:pointer;">
                  <el-badge :value="msgUnreadCount" :hidden="msgUnreadCount === 0" :max="99">
                    <el-icon :size="20"><Bell /></el-icon>
                  </el-badge>
                </div>
              </template>
              <div class="msg-popover">
                <div class="msg-popover-tabs">
                  <button
                    :class="['msg-tab', msgPopoverTab === 'unread' && 'active']"
                    @click="msgPopoverTab = 'unread'"
                  >未读消息<span v-if="msgUnreadCount" class="msg-tab-badge">{{ msgUnreadCount }}</span></button>
                  <button
                    :class="['msg-tab', msgPopoverTab === 'all' && 'active']"
                    @click="msgPopoverTab = 'all'"
                  >全部消息</button>
                  <span class="msg-tab-spacer" />
                  <button v-if="msgUnreadCount > 0" class="msg-mark-all" @click="handlePopoverMarkAllRead">全部已读</button>
                </div>
                <div class="msg-popover-list" v-loading="msgPopoverLoading">
                  <template v-if="msgPopoverList.length">
                    <div
                      v-for="msg in msgPopoverList"
                      :key="msg.id"
                      class="msg-popover-item"
                      :class="{ unread: !msg.is_read }"
                      @click="handlePopoverItemClick(msg)"
                    >
                      <div class="msg-item-header">
                        <el-tag :type="popoverLevelType(msg.level)" size="small" effect="light" class="msg-level-tag">{{ popoverLevelLabel(msg.level) }}</el-tag>
                        <span class="msg-item-time">{{ formatMsgTime(msg.created_at) }}</span>
                      </div>
                      <div class="msg-item-title">{{ msg.title }}</div>
                      <div class="msg-item-content" v-if="msg.content">{{ msg.content }}</div>
                    </div>
                  </template>
                  <div v-else class="msg-popover-empty">暂无消息</div>
                </div>
                <div class="msg-popover-footer">
                  <el-button type="primary" link @click="router.push('/system-center')">查看全部 →</el-button>
                </div>
              </div>
            </el-popover>
            <div class="lark-action-item">
               <el-icon :size="20"><QuestionFilled /></el-icon>
            </div>
          </div>

          <el-dropdown @command="handleCommand" trigger="hover" class="lark-user-dropdown">
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
import { ElMessage, ElMessageBox, ElNotification } from 'element-plus'
import {
  DataLine, User, Setting, Fold, Expand, Box, UserFilled,
  Search, Bell, SwitchButton, Stamp, Management, Goods, List, QuestionFilled,
  ChatDotRound, Monitor, Link, Document, DocumentChecked, Star, Tickets
} from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'
import request from '@/utils/request'
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

// ========== 系统消息悬浮窗 ==========
const msgUnreadCount = ref(0)
const msgPopoverTab = ref('unread')
const msgPopoverLoading = ref(false)
const msgPopoverUnread = ref([])
const msgPopoverAll = ref([])
let msgPollTimer = null

const msgPopoverList = computed(() =>
  msgPopoverTab.value === 'unread' ? msgPopoverUnread.value : msgPopoverAll.value
)

async function fetchMsgUnreadCount() {
  try {
    const res = await request({ url: '/api/system-messages/unread-count', method: 'get', silentError: true })
    msgUnreadCount.value = res.data?.count || 0
  } catch { msgUnreadCount.value = 0 }
}

async function fetchMsgPopoverData() {
  msgPopoverLoading.value = true
  try {
    const [unreadRes, allRes] = await Promise.all([
      request({ url: '/api/system-messages', method: 'get', params: { is_read: 0, page: 1, page_size: 8 }, silentError: true }),
      request({ url: '/api/system-messages', method: 'get', params: { page: 1, page_size: 8 }, silentError: true }),
    ])
    msgPopoverUnread.value = unreadRes.data?.items || []
    msgPopoverAll.value = allRes.data?.items || []
    msgUnreadCount.value = unreadRes.data?.total || 0
  } catch { /* ignore */ } finally { msgPopoverLoading.value = false }
}

function onMsgPopoverShow() {
  fetchMsgPopoverData()
}

async function handlePopoverMarkAllRead() {
  try {
    await request({ url: '/api/system-messages/read-all', method: 'put' })
    msgPopoverUnread.value = []
    msgPopoverAll.value.forEach(m => { m.is_read = 1 })
    msgUnreadCount.value = 0
  } catch { /* ignore */ }
}

async function handlePopoverItemClick(msg) {
  if (!msg.is_read) {
    try {
      await request({ url: `/api/system-messages/${msg.id}/read`, method: 'put' })
      msg.is_read = 1
      msgUnreadCount.value = Math.max(0, msgUnreadCount.value - 1)
      msgPopoverUnread.value = msgPopoverUnread.value.filter(m => !m.is_read)
    } catch { /* ignore */ }
  }
}

function popoverLevelType(level) {
  return { error: 'danger', warning: 'warning', info: 'info', success: 'success' }[level] || ''
}
function popoverLevelLabel(level) {
  return { error: '错误', warning: '警告', info: '信息', success: '成功' }[level] || level
}
function formatMsgTime(t) {
  if (!t) return ''
  const s = String(t)
  return s.includes('T') ? s.replace('T', ' ').slice(0, 19) : s.slice(0, 19)
}

function startMsgPoll() {
  fetchMsgUnreadCount()
  msgPollTimer = setInterval(fetchMsgUnreadCount, 60000)
}

const activeMenu = computed(() => {
  const p = route.path
  if (p === '/customers' || p === '/wechat-rooms') return '/users'
  if (p.startsWith('/sales/')) return '/sales'
  if (p.startsWith('/shipments/')) return '/shipments'
  if (p.startsWith('/unshipped-report/')) return '/unshipped-report'
  if (p.startsWith('/config-')) return '/config-wechat'
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

function onMsgUnreadChanged(e) {
  const count = e.detail?.count
  if (typeof count === 'number') {
    msgUnreadCount.value = count
  }
}

// ========== 企微掉线弹窗通知 ==========
let wechatNotifyWs = null
let wechatNotifyReconnectTimer = null
let _wechatOfflineNotification = null

function connectWechatNotifyWs() {
  if (wechatNotifyWs && wechatNotifyWs.readyState <= 1) return
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  wechatNotifyWs = new WebSocket(`${proto}://${location.host}/ws/notify`)
  wechatNotifyWs.onmessage = (evt) => {
    try {
      const msg = JSON.parse(evt.data)
      // 转发给全局，Dashboard 等组件可监听
      window.dispatchEvent(new CustomEvent('ws_notify', { detail: msg }))
      if (msg.event === 'wechat_offline') {
        showWechatOfflineNotification(msg.data?.error || '')
      } else if (msg.event === 'wechat_online') {
        closeWechatOfflineNotification()
        ElNotification.success({
          title: '企业微信已恢复',
          message: '企业微信连接已自动恢复正常',
          position: 'bottom-right',
          duration: 5000,
        })
      }
    } catch { /* ignore */ }
  }
  wechatNotifyWs.onclose = () => {
    clearTimeout(wechatNotifyReconnectTimer)
    wechatNotifyReconnectTimer = setTimeout(connectWechatNotifyWs, 3000)
  }
  wechatNotifyWs.onerror = () => { /* onclose will handle reconnect */ }
}

function showWechatOfflineNotification(errorMsg) {
  closeWechatOfflineNotification()
  _wechatOfflineNotification = ElNotification.warning({
    title: '企业微信已掉线',
    message: errorMsg
      ? `检测原因：${errorMsg}，自动恢复失败，请检查企微服务或手动重连。`
      : '企业微信连接异常，请前往外部配置页面检查。',
    position: 'bottom-right',
    duration: 0,
    showClose: true,
  })
}

function closeWechatOfflineNotification() {
  if (_wechatOfflineNotification) {
    _wechatOfflineNotification.close()
    _wechatOfflineNotification = null
  }
}

async function checkInitialWechatStatus() {
  try {
    const res = await request.get('/api/dashboard/stats', { params: { range: '7d' } })
    const data = res.data || {}
    if (!data.wechat_online && !data.wechat_recovering) {
      showWechatOfflineNotification(data.wechat_error || '')
    }
  } catch { /* ignore */ }
}

onMounted(() => {
  userStore.fetchUserInfo(true).catch(() => {})
  window.addEventListener('keydown', handleGlobalShortcut)
  window.addEventListener('msg-unread-changed', onMsgUnreadChanged)
  startMsgPoll()
  connectWechatNotifyWs()
  checkInitialWechatStatus()
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleGlobalShortcut)
  window.removeEventListener('msg-unread-changed', onMsgUnreadChanged)
  clearTimeout(searchTimer)
  clearInterval(msgPollTimer)
  clearTimeout(wechatNotifyReconnectTimer)
  if (wechatNotifyWs) { wechatNotifyWs.close(); wechatNotifyWs = null }
  closeWechatOfflineNotification()
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
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 8px;
  cursor: pointer;
  flex-shrink: 0;
}

.logo-img {
  width: 38px;
  height: 38px;
  border-radius: var(--lark-radius);
  margin-right: 8px;
  flex-shrink: 0;
  object-fit: contain;
}

.logo-text {
  font-size: 24px;
  font-weight: 700;
  color: var(--lark-text-primary);
  margin: 0;
  white-space: nowrap;
  letter-spacing: 3px;
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
  overflow: auto;
}

.lark-page-wrapper {
  height: 100%;
  width: 100%;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: auto;
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

/* ===== 系统消息悬浮窗 ===== */
.msg-popover {
  margin: -12px;
}

.msg-popover-tabs {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 12px 16px 0;
  border-bottom: 1px solid var(--lark-border-light);
}

.msg-tab {
  background: none;
  border: none;
  padding: 8px 12px;
  font-size: 13px;
  font-weight: 500;
  color: var(--lark-text-secondary);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 4px;
}

.msg-tab:hover {
  color: var(--lark-text-primary);
}

.msg-tab.active {
  color: var(--lark-primary);
  border-bottom-color: var(--lark-primary);
}

.msg-tab-badge {
  background: var(--el-color-danger);
  color: #fff;
  font-size: 11px;
  min-width: 16px;
  height: 16px;
  line-height: 16px;
  border-radius: 8px;
  padding: 0 4px;
  text-align: center;
}

.msg-tab-spacer {
  flex: 1;
}

.msg-mark-all {
  background: none;
  border: none;
  font-size: 12px;
  color: var(--lark-primary);
  cursor: pointer;
  padding: 4px 8px;
  margin-bottom: 4px;
}

.msg-mark-all:hover {
  opacity: 0.8;
}

.msg-popover-list {
  max-height: 360px;
  overflow-y: auto;
  min-height: 80px;
}

.msg-popover-item {
  padding: 10px 16px;
  border-bottom: 1px solid var(--lark-border-light);
  cursor: pointer;
  transition: background 0.15s;
}

.msg-popover-item:last-child {
  border-bottom: none;
}

.msg-popover-item:hover {
  background: var(--lark-bg-hover);
}

.msg-popover-item.unread {
  background: #f0f7ff;
}

.msg-popover-item.unread:hover {
  background: #e4f0ff;
}

.msg-item-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}

.msg-level-tag {
  transform: scale(0.85);
  transform-origin: left center;
}

.msg-item-time {
  font-size: 11px;
  color: var(--lark-text-disabled);
  flex-shrink: 0;
}

.msg-item-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--lark-text-primary);
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.msg-item-content {
  font-size: 12px;
  color: var(--lark-text-secondary);
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.msg-popover-empty {
  text-align: center;
  padding: 32px 0;
  font-size: 13px;
  color: var(--lark-text-disabled);
}

.msg-popover-footer {
  text-align: center;
  padding: 8px 0;
  border-top: 1px solid var(--lark-border-light);
}
</style>
