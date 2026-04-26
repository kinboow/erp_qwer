<template>
  <div class="lark-logs">
    <div class="lark-page-header">
      <div class="header-title">系统日志</div>
      <div class="header-desc">查看系统运行日志与用户操作记录</div>
    </div>

    <div class="lark-table-panel">
      <el-tabs v-model="activeTab" @tab-change="handleTabChange">
        <el-tab-pane label="系统日志" name="system">
          <!-- 工具栏 -->
          <div class="lark-toolbar">
            <div class="toolbar-left">
              <el-select v-model="systemFilter.level" placeholder="日志级别" clearable style="width: 120px;" @change="fetchSystemLogs">
                <el-option label="全部" value="" />
                <el-option label="ERROR" value="error" />
                <el-option label="WARN" value="warn" />
                <el-option label="INFO" value="info" />
              </el-select>
              <el-date-picker
                v-model="systemFilter.dateRange"
                type="daterange"
                range-separator="至"
                start-placeholder="开始日期"
                end-placeholder="结束日期"
                value-format="YYYY-MM-DD"
                style="width: 260px;"
                @change="fetchSystemLogs"
              />
              <div class="lark-search-input-wrap">
                <el-icon class="search-icon"><Search /></el-icon>
                <input
                  v-model="systemFilter.keyword"
                  class="lark-input"
                  placeholder="搜索日志内容"
                  @keyup.enter="fetchSystemLogs"
                />
              </div>
            </div>
            <div class="toolbar-right">
              <el-button :icon="Refresh" @click="fetchSystemLogs" :loading="systemLoading">刷新</el-button>
            </div>
          </div>

          <!-- 系统日志表格 -->
          <el-table :data="systemLogs" v-loading="systemLoading" stripe class="lark-table">
            <el-table-column label="时间" prop="timestamp" width="180">
              <template #default="{ row }">
                <span class="log-time">{{ row.timestamp }}</span>
              </template>
            </el-table-column>
            <el-table-column label="级别" prop="level" width="100">
              <template #default="{ row }">
                <el-tag :type="levelTagType(row.level)" size="small" effect="plain">
                  {{ row.level?.toUpperCase() }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="服务" prop="service" width="140" />
            <el-table-column label="内容" prop="message" min-width="300" show-overflow-tooltip />
          </el-table>

          <div class="lark-pagination">
            <el-pagination
              v-model:current-page="systemPagination.page"
              v-model:page-size="systemPagination.pageSize"
              :total="systemPagination.total"
              :page-sizes="[20, 50, 100]"
              layout="total, sizes, prev, pager, next"
              @size-change="fetchSystemLogs"
              @current-change="fetchSystemLogs"
            />
          </div>
        </el-tab-pane>

        <el-tab-pane label="操作日志" name="operation">
          <!-- 工具栏 -->
          <div class="lark-toolbar">
            <div class="toolbar-left">
              <el-select v-model="opFilter.module" placeholder="功能模块" clearable style="width: 140px;" @change="fetchOpLogs">
                <el-option label="全部" value="" />
                <el-option label="用户管理" value="user" />
                <el-option label="角色管理" value="role" />
                <el-option label="企微配置" value="wechat" />
                <el-option label="登录认证" value="auth" />
              </el-select>
              <el-select v-model="opFilter.action" placeholder="操作类型" clearable style="width: 120px;" @change="fetchOpLogs">
                <el-option label="全部" value="" />
                <el-option label="新增" value="create" />
                <el-option label="修改" value="update" />
                <el-option label="删除" value="delete" />
                <el-option label="登录" value="login" />
                <el-option label="登出" value="logout" />
              </el-select>
              <el-date-picker
                v-model="opFilter.dateRange"
                type="daterange"
                range-separator="至"
                start-placeholder="开始日期"
                end-placeholder="结束日期"
                value-format="YYYY-MM-DD"
                style="width: 260px;"
                @change="fetchOpLogs"
              />
              <div class="lark-search-input-wrap">
                <el-icon class="search-icon"><Search /></el-icon>
                <input
                  v-model="opFilter.keyword"
                  class="lark-input"
                  placeholder="搜索操作人或描述"
                  @keyup.enter="fetchOpLogs"
                />
              </div>
            </div>
            <div class="toolbar-right">
              <el-button :icon="Refresh" @click="fetchOpLogs" :loading="opLoading">刷新</el-button>
            </div>
          </div>

          <!-- 操作日志表格 -->
          <el-table :data="opLogs" v-loading="opLoading" stripe class="lark-table">
            <el-table-column label="时间" prop="created_at" width="180">
              <template #default="{ row }">
                <span class="log-time">{{ row.created_at }}</span>
              </template>
            </el-table-column>
            <el-table-column label="操作人" prop="username" width="120" />
            <el-table-column label="模块" prop="module" width="120">
              <template #default="{ row }">
                <span>{{ moduleLabel(row.module) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" prop="action" width="100">
              <template #default="{ row }">
                <el-tag :type="actionTagType(row.action)" size="small" effect="plain">
                  {{ actionLabel(row.action) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="描述" prop="description" min-width="280" show-overflow-tooltip />
            <el-table-column label="IP 地址" prop="ip" width="140" />
          </el-table>

          <div class="lark-pagination">
            <el-pagination
              v-model:current-page="opPagination.page"
              v-model:page-size="opPagination.pageSize"
              :total="opPagination.total"
              :page-sizes="[20, 50, 100]"
              layout="total, sizes, prev, pager, next"
              @size-change="fetchOpLogs"
              @current-change="fetchOpLogs"
            />
          </div>
        </el-tab-pane>

        <el-tab-pane label="消息日志" name="message">
          <div class="lark-toolbar">
            <div class="toolbar-left">
              <el-select v-model="messageFilter.source" placeholder="消息来源" clearable style="width: 140px;" @change="fetchMessageLogs">
                <el-option label="全部" value="" />
                <el-option label="HTTP 回调" value="http_callback" />
                <el-option label="WebSocket" value="websocket" />
              </el-select>
              <el-select v-model="messageFilter.message_type" placeholder="消息类型" clearable style="width: 140px;" @change="fetchMessageLogs">
                <el-option label="全部" value="" />
                <el-option label="文本" value="text" />
                <el-option label="图片" value="image" />
                <el-option label="文件" value="file" />
                <el-option label="未知" value="unknown" />
              </el-select>
              <el-date-picker
                v-model="messageFilter.dateRange"
                type="daterange"
                range-separator="至"
                start-placeholder="开始日期"
                end-placeholder="结束日期"
                value-format="YYYY-MM-DD"
                style="width: 260px;"
                @change="fetchMessageLogs"
              />
              <div class="lark-search-input-wrap">
                <el-icon class="search-icon"><Search /></el-icon>
                <input
                  v-model="messageFilter.keyword"
                  class="lark-input"
                  placeholder="搜索群名、发送人、消息内容"
                  @keyup.enter="fetchMessageLogs"
                />
              </div>
            </div>
            <div class="toolbar-right">
              <el-button :icon="Refresh" @click="fetchMessageLogs" :loading="messageLoading">刷新</el-button>
            </div>
          </div>

          <el-table :data="messageLogs" v-loading="messageLoading" stripe class="lark-table">
            <el-table-column type="expand" width="52">
              <template #default="{ row }">
                <pre class="message-payload-block">{{ formatPayload(row.payload) }}</pre>
              </template>
            </el-table-column>
            <el-table-column label="时间" prop="created_at" width="180">
              <template #default="{ row }">
                <span class="log-time">{{ row.created_at }}</span>
              </template>
            </el-table-column>
            <el-table-column label="来源" prop="source" width="120">
              <template #default="{ row }">
                <el-tag size="small" effect="plain">{{ messageSourceLabel(row.source) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="类型" prop="message_type" width="100">
              <template #default="{ row }">
                <el-tag :type="messageTypeTagType(row.message_type)" size="small" effect="plain">
                  {{ messageTypeLabel(row.message_type) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="发送人/群" min-width="220" show-overflow-tooltip>
              <template #default="{ row }">
                <span>{{ row.sender_name || row.sender_id || '-' }}</span>
                <span v-if="row.room_name || row.room_id" style="color:var(--lark-text-secondary);margin-left:4px;">/ {{ row.room_name || row.room_id }}</span>
              </template>
            </el-table-column>
            <el-table-column label="内容" prop="content_preview" min-width="320" show-overflow-tooltip />
            <el-table-column label="实例" prop="instance_id" width="140" show-overflow-tooltip />
          </el-table>

          <div class="lark-pagination">
            <el-pagination
              v-model:current-page="messagePagination.page"
              v-model:page-size="messagePagination.pageSize"
              :total="messagePagination.total"
              :page-sizes="[20, 50, 100]"
              layout="total, sizes, prev, pager, next"
              @size-change="fetchMessageLogs"
              @current-change="fetchMessageLogs"
            />
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, watch } from 'vue'
import { Search, Refresh } from '@element-plus/icons-vue'
import request from '@/utils/request'

const activeTab = ref('system')

// ========== 系统日志 ==========
const systemLoading = ref(false)
const systemLogs = ref([])
const systemFilter = reactive({ level: '', keyword: '', dateRange: null })
const systemPagination = reactive({ page: 1, pageSize: 20, total: 0 })

async function fetchSystemLogs() {
  systemLoading.value = true
  try {
    const params = {
      page: systemPagination.page,
      pageSize: systemPagination.pageSize
    }
    if (systemFilter.level) params.level = systemFilter.level
    if (systemFilter.keyword) params.keyword = systemFilter.keyword
    if (systemFilter.dateRange) {
      params.startDate = systemFilter.dateRange[0]
      params.endDate = systemFilter.dateRange[1]
    }
    const res = await request({ url: '/api/logs/system', method: 'get', params })
    systemLogs.value = res.data?.list || []
    systemPagination.total = res.data?.total || 0
  } catch {
    systemLogs.value = []
    systemPagination.total = 0
  } finally {
    systemLoading.value = false
  }
}

async function fetchMessageLogs() {
  messageLoading.value = true
  try {
    const params = {
      page: messagePagination.page,
      pageSize: messagePagination.pageSize
    }
    if (messageFilter.source) params.source = messageFilter.source
    if (messageFilter.message_type) params.message_type = messageFilter.message_type
    if (messageFilter.keyword) params.keyword = messageFilter.keyword
    if (messageFilter.dateRange) {
      params.startDate = messageFilter.dateRange[0]
      params.endDate = messageFilter.dateRange[1]
    }
    const res = await request({ url: '/api/logs/messages', method: 'get', params })
    messageLogs.value = res.data?.list || []
    messagePagination.total = res.data?.total || 0
  } catch {
    messageLogs.value = []
    messagePagination.total = 0
  } finally {
    messageLoading.value = false
  }
}

// ========== 操作日志 ==========
const opLoading = ref(false)
const opLogs = ref([])
const opFilter = reactive({ module: '', action: '', keyword: '', dateRange: null })
const opPagination = reactive({ page: 1, pageSize: 20, total: 0 })

const messageLoading = ref(false)
const messageLogs = ref([])
const messageFilter = reactive({ source: '', message_type: '', keyword: '', dateRange: null })
const messagePagination = reactive({ page: 1, pageSize: 20, total: 0 })

async function fetchOpLogs() {
  opLoading.value = true
  try {
    const params = {
      page: opPagination.page,
      pageSize: opPagination.pageSize
    }
    if (opFilter.module) params.module = opFilter.module
    if (opFilter.action) params.action = opFilter.action
    if (opFilter.keyword) params.keyword = opFilter.keyword
    if (opFilter.dateRange) {
      params.startDate = opFilter.dateRange[0]
      params.endDate = opFilter.dateRange[1]
    }
    const res = await request({ url: '/api/logs/operation', method: 'get', params })
    opLogs.value = res.data?.list || []
    opPagination.total = res.data?.total || 0
  } catch {
    opLogs.value = []
    opPagination.total = 0
  } finally {
    opLoading.value = false
  }
}

// ========== 辅助方法 ==========
function levelTagType(level) {
  const map = { error: 'danger', warn: 'warning', info: 'info', debug: '' }
  return map[level] || ''
}

function actionTagType(action) {
  const map = { create: 'success', update: 'warning', delete: 'danger', login: 'info', logout: '' }
  return map[action] || ''
}

function actionLabel(action) {
  const map = { create: '新增', update: '修改', delete: '删除', login: '登录', logout: '登出' }
  return map[action] || action
}

function moduleLabel(mod) {
  const map = { user: '用户管理', role: '角色管理', wechat: '企微配置', auth: '登录认证' }
  return map[mod] || mod
}

function messageSourceLabel(source) {
  const map = { http_callback: 'HTTP 回调', websocket: 'WebSocket' }
  return map[source] || source || '-'
}

function messageTypeLabel(type) {
  const map = { text: '文本', image: '图片', file: '文件', unknown: '未知' }
  return map[type] || type || '-'
}

function messageTypeTagType(type) {
  const map = { text: 'info', image: 'success', file: 'warning', unknown: '' }
  return map[type] || ''
}

function formatPayload(payload) {
  try {
    return JSON.stringify(payload || {}, null, 2)
  } catch {
    return String(payload || '')
  }
}

function handleTabChange(tab) {
  if (tab === 'system') fetchSystemLogs()
  else if (tab === 'operation') fetchOpLogs()
  else fetchMessageLogs()
}

// ========== 实时通知 WebSocket ==========
let notifyWs = null
let reconnectTimer = null

function connectNotifyWs() {
  if (notifyWs && notifyWs.readyState <= 1) return
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  notifyWs = new WebSocket(`${proto}://${location.host}/ws/notify`)
  notifyWs.onmessage = (evt) => {
    try {
      const msg = JSON.parse(evt.data)
      if (msg.event === 'new_message_log' && activeTab.value === 'message') {
        fetchMessageLogs()
      }
    } catch {}
  }
  notifyWs.onclose = () => {
    reconnectTimer = setTimeout(connectNotifyWs, 3000)
  }
  notifyWs.onerror = () => {
    notifyWs?.close()
  }
}

function disconnectNotifyWs() {
  if (reconnectTimer) clearTimeout(reconnectTimer)
  reconnectTimer = null
  if (notifyWs) {
    notifyWs.onclose = null
    notifyWs.close()
    notifyWs = null
  }
}

onMounted(() => {
  fetchSystemLogs()
  connectNotifyWs()
})

onUnmounted(() => {
  disconnectNotifyWs()
})
</script>

<style scoped>
.lark-logs {
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

.message-payload-block {
  margin: 0;
  padding: 12px;
  border-radius: var(--lark-radius);
  background: var(--lark-bg-subtle);
  color: var(--lark-text-primary);
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.lark-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

:deep(.el-tabs__header) {
  margin-bottom: 16px;
}

:deep(.el-tabs__item) {
  font-size: 14px;
  font-weight: 500;
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
