<template>
  <div class="lark-sys-messages">

    <div class="lark-table-panel">
      <!-- 工具栏 -->
      <div class="lark-toolbar">
        <div class="toolbar-left">
          <el-select v-model="filter.level" placeholder="消息级别" clearable style="width: 120px;" @change="fetchMessages">
            <el-option label="全部" value="" />
            <el-option label="成功" value="success" />
            <el-option label="错误" value="error" />
            <el-option label="警告" value="warning" />
            <el-option label="信息" value="info" />
          </el-select>
          <el-select v-model="filter.source" placeholder="消息来源" clearable style="width: 140px;" @change="fetchMessages">
            <el-option label="全部" value="" />
            <el-option label="ERP 同步" value="erp_sync" />
            <el-option label="系统" value="system" />
          </el-select>
          <el-select v-model="filter.is_read" placeholder="状态" clearable style="width: 120px;" @change="fetchMessages">
            <el-option label="全部" value="" />
            <el-option label="未读" :value="0" />
            <el-option label="已读" :value="1" />
          </el-select>
          <div class="lark-search-input-wrap">
            <el-icon class="search-icon"><Search /></el-icon>
            <input
              v-model="filter.keyword"
              class="lark-input"
              placeholder="搜索消息内容"
              @keyup.enter="fetchMessages"
            />
          </div>
        </div>
        <div class="toolbar-right">
          <el-button type="primary" plain size="small" @click="handleMarkAllRead" :disabled="unreadCount === 0">
            全部已读
          </el-button>
          <el-button :icon="Refresh" @click="fetchMessages" :loading="loading">刷新</el-button>
        </div>
      </div>

      <!-- 消息表格 -->
      <el-table :data="messages" v-loading="loading" stripe class="lark-table"
        :tooltip-options="{ placement: 'top', popperOptions: { modifiers: [{ name: 'flip', options: { fallbackPlacements: ['bottom', 'left', 'right'] } }] } }">
        <el-table-column label="级别" prop="level" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="levelTagType(row.level)" size="small" effect="light">
              {{ levelLabel(row.level) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="来源" prop="source" width="110" align="center">
          <template #default="{ row }">
            {{ sourceLabel(row.source) }}
          </template>
        </el-table-column>
        <el-table-column label="标题" prop="title" min-width="200">
          <template #default="{ row }">
            <span :class="{ 'msg-unread': !row.is_read }">{{ row.title }}</span>
          </template>
        </el-table-column>
        <el-table-column label="详情" prop="content" min-width="300" show-overflow-tooltip />
        <el-table-column label="时间" prop="created_at" width="180">
          <template #default="{ row }">
            <span class="log-time">{{ row.created_at }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.is_read" type="info" size="small" effect="plain">已读</el-tag>
            <el-tag v-else type="danger" size="small" effect="light">未读</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center">
          <template #default="{ row }">
            <el-button
              v-if="!row.is_read"
              type="primary"
              link
              size="small"
              @click="handleMarkRead(row)"
            >已读</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="lark-pagination">
        <el-pagination
          v-model:current-page="pagination.page"
          :page-size="pagination.pageSize"
          :total="pagination.total"
          layout="total, prev, pager, next"
          @current-change="fetchMessages"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { Search, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import request from '@/utils/request'

const loading = ref(false)
const messages = ref([])
const unreadCount = ref(0)
const filter = reactive({ level: '', source: '', is_read: '', keyword: '' })
const pagination = reactive({ page: 1, pageSize: 20, total: 0 })

async function fetchMessages() {
  loading.value = true
  try {
    const params = { page: pagination.page, page_size: pagination.pageSize }
    if (filter.level) params.level = filter.level
    if (filter.source) params.source = filter.source
    if (filter.is_read !== '' && filter.is_read !== null) params.is_read = filter.is_read
    if (filter.keyword) params.keyword = filter.keyword
    const res = await request({ url: '/api/system-messages', method: 'get', params })
    messages.value = res.data?.items || []
    pagination.total = res.data?.total || 0
  } catch {
    messages.value = []
    pagination.total = 0
  } finally {
    loading.value = false
  }
  fetchUnreadCount()
}

async function fetchUnreadCount() {
  try {
    const res = await request({ url: '/api/system-messages/unread-count', method: 'get' })
    unreadCount.value = res.data?.count || 0
  } catch {
    unreadCount.value = 0
  }
}

async function handleMarkRead(row) {
  try {
    await request({ url: `/api/system-messages/${row.id}/read`, method: 'put' })
    row.is_read = 1
    unreadCount.value = Math.max(0, unreadCount.value - 1)
    window.dispatchEvent(new CustomEvent('msg-unread-changed', { detail: { count: unreadCount.value } }))
  } catch {
    ElMessage.error('标记失败')
  }
}

async function handleMarkAllRead() {
  try {
    await request({ url: '/api/system-messages/read-all', method: 'put' })
    messages.value.forEach(m => { m.is_read = 1 })
    unreadCount.value = 0
    window.dispatchEvent(new CustomEvent('msg-unread-changed', { detail: { count: 0 } }))
    ElMessage.success('已全部标记为已读')
  } catch {
    ElMessage.error('操作失败')
  }
}

function levelTagType(level) {
  const map = { error: 'danger', warning: 'warning', info: 'info', success: 'success' }
  return map[level] || ''
}

function levelLabel(level) {
  const map = { error: '错误', warning: '警告', info: '信息', success: '成功' }
  return map[level] || level
}

function sourceLabel(source) {
  const map = { erp_sync: 'ERP 同步', system: '系统', wechat: '企业微信' }
  return map[source] || source || '-'
}

onMounted(() => {
  fetchMessages()
})
</script>

<style scoped>
.lark-sys-messages {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.lark-page-header { margin-bottom: 4px; }

.header-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--lark-text-primary);
  margin-bottom: 6px;
}

.header-desc {
  font-size: 13px;
  color: var(--lark-text-secondary);
}

.lark-table-panel {
  background: var(--lark-bg-base);
  border-radius: var(--lark-radius-lg);
  padding: 20px 24px;
}

.lark-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  gap: 12px;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.lark-search-input-wrap {
  position: relative;
  display: flex;
  align-items: center;
}

.lark-search-input-wrap .search-icon {
  position: absolute;
  left: 10px;
  color: var(--lark-text-disabled);
  font-size: 14px;
  pointer-events: none;
}

.lark-input {
  height: 32px;
  padding: 0 12px 0 32px;
  border: 1px solid var(--lark-border-light);
  border-radius: var(--lark-radius);
  background: var(--lark-bg-base);
  font-size: 13px;
  color: var(--lark-text-primary);
  outline: none;
  width: 200px;
  transition: border-color 0.2s;
}

.lark-input:focus {
  border-color: var(--lark-primary);
}

.log-time {
  font-size: 13px;
  color: var(--lark-text-secondary);
  font-family: monospace;
}

.msg-unread {
  font-weight: 600;
}

.lark-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

:deep(.el-table) {
  --el-table-border-color: var(--lark-border-light);
  --el-table-header-bg-color: var(--lark-bg-subtle);
  font-size: 13px;
}

:deep(.el-table th.el-table__cell) {
  font-weight: 600;
  color: var(--lark-text-primary);
}
</style>
