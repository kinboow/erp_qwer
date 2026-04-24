<template>
  <el-container class="lark-layout">
    <!-- 侧边栏：极简、浅灰色背景、无边框 -->
    <el-aside :width="isCollapse ? '68px' : '240px'" class="lark-sidebar" :class="{ 'is-collapse': isCollapse }">
      <div class="lark-logo">
        <div class="logo-box">
          <el-icon color="#fff" :size="20"><Box /></el-icon>
        </div>
        <transition name="fade">
          <h1 v-show="!isCollapse" class="logo-text">Factory ERP</h1>
        </transition>
      </div>

      <el-scrollbar class="lark-menu-scroll">
        <el-menu
          :default-active="activeMenu"
          class="lark-menu"
          :collapse="isCollapse"
          :collapse-transition="false"
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
              <el-icon><Goods /></el-icon>
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
              <template #title>外部服务配置</template>
            </el-menu-item>
            <el-menu-item index="/logs">
              <el-icon><Document /></el-icon>
              <template #title>系统日志</template>
            </el-menu-item>
          </el-sub-menu>

        </el-menu>
      </el-scrollbar>

      <!-- 底部折叠按钮，飞书风格 -->
      <div class="lark-collapse-wrap">
        <div class="lark-collapse-btn" @click="toggleCollapse">
          <el-icon :size="16"><Fold v-if="!isCollapse"/><Expand v-else/></el-icon>
          <span v-show="!isCollapse">收起菜单</span>
        </div>
      </div>
    </el-aside>

    <el-container class="lark-main-container">
      <!-- 顶部导航：无阴影、极简白 -->
      <el-header class="lark-header">
        <div class="lark-header-left">
          <!-- 面包屑更轻量 -->
          <el-breadcrumb separator="/">
            <el-breadcrumb-item :to="{ path: '/' }">工作台</el-breadcrumb-item>
            <el-breadcrumb-item v-if="route.meta.title && route.path !== '/dashboard'">
              <span style="color: var(--lark-text-primary); font-weight: 600;">{{ route.meta.title }}</span>
            </el-breadcrumb-item>
          </el-breadcrumb>
        </div>

        <div class="lark-header-right">
          <div class="lark-search-box">
             <el-icon class="search-icon"><Search /></el-icon>
             <input type="text" placeholder="搜索应用、功能或文档..." class="lark-search-input" />
             <span class="search-shortcut">⌘K</span>
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
                  <div class="user-role">{{ userStore.roles.includes('super_admin') ? '系统超级管理员' : '普通用户' }}</div>
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
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  DataLine, User, Setting, Fold, Expand, Box, UserFilled,
  Search, Bell, SwitchButton, Stamp, Management, Goods, List, QuestionFilled,
  ChatDotRound, Monitor, Link, Document
} from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const isCollapse = ref(false)

const activeMenu = computed(() => route.path === '/customers' ? '/users' : route.path)

const handleUndeveloped = () => {
  ElMessage.warning('该功能暂未开发，敬请期待！')
  // 阻止导航，回到当前页
  router.replace(route.fullPath)
}

const toggleCollapse = () => {
  isCollapse.value = !isCollapse.value
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

/* 折叠态菜单项 */
:deep(.el-menu--collapse > .el-menu-item),
:deep(.el-menu--collapse > .el-sub-menu > .el-sub-menu__title) {
  width: 44px;
  height: 44px;
  line-height: 44px;
  padding: 0 !important;
  margin: 0 auto 4px;
  display: flex;
  justify-content: center;
  align-items: center;
  border-radius: var(--lark-radius);
}

:deep(.el-menu--collapse > .el-menu-item .el-icon),
:deep(.el-menu--collapse > .el-sub-menu > .el-sub-menu__title .el-icon) {
  margin-right: 0;
}

/* 侧边栏底部折叠 */
.lark-collapse-wrap {
  padding: 12px;
  border-top: 1px solid var(--lark-border-light);
  flex-shrink: 0;
}

.lark-collapse-btn {
  height: 36px;
  border-radius: var(--lark-radius);
  display: flex;
  align-items: center;
  padding: 0 12px;
  cursor: pointer;
  color: var(--lark-text-regular);
  font-size: 14px;
  transition: background-color 0.2s;
}

.lark-collapse-btn:hover {
  background-color: var(--lark-bg-hover);
  color: var(--lark-text-primary);
}

.lark-collapse-btn span {
  margin-left: 10px;
  white-space: nowrap;
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
