<template>
  <div class="lark-ai-logs">
    <div class="logs-toolbar">
      <div class="toolbar-left">
        <el-select v-model="filter.caller" placeholder="调用来源" clearable style="width: 150px" @change="handleSearch">
          <el-option label="全部" value="" />
          <el-option label="测试连接" value="test_connection" />
          <el-option label="批量解析" value="parse_batch" />
          <el-option label="文本解析" value="parse_text" />
          <el-option label="图片解析" value="parse_image" />
          <el-option label="表格解析" value="parse_excel" />
          <el-option label="二次解析" value="reparse_with_hints" />
        </el-select>
        <el-select v-model="filter.status" placeholder="状态" clearable style="width: 120px" @change="handleSearch">
          <el-option label="全部" value="" />
          <el-option label="成功" value="success" />
          <el-option label="失败" value="error" />
        </el-select>
      </div>
      <div class="toolbar-right">
        <span class="total-hint">共 {{ total }} 条记录</span>
        <el-button :icon="Refresh" @click="fetchLogs" :loading="loading">刷新</el-button>
      </div>
    </div>

    <el-table :data="logs" v-loading="loading" stripe class="lark-table" empty-text="暂无调用日志"
      :tooltip-options="{ placement: 'top', popperOptions: { modifiers: [{ name: 'flip', options: { fallbackPlacements: ['bottom', 'left', 'right'] } }] } }">
      <el-table-column label="时间" prop="called_at" width="170" />
      <el-table-column label="模型" prop="model" width="160" show-overflow-tooltip />
      <el-table-column label="来源" width="130">
        <template #default="{ row }">
          <el-tag size="small" :type="callerTagType(row.caller)">{{ callerLabel(row.caller) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="80" align="center">
        <template #default="{ row }">
          <el-tag size="small" :type="row.status === 'success' ? 'success' : 'danger'">
            {{ row.status === 'success' ? '成功' : '失败' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="耗时" width="90" align="right">
        <template #default="{ row }">
          {{ row.duration_ms >= 1000 ? (row.duration_ms / 1000).toFixed(1) + 's' : row.duration_ms + 'ms' }}
        </template>
      </el-table-column>
      <el-table-column label="Tokens" width="150">
        <template #default="{ row }">
          <span v-if="row.total_tokens" class="token-text">
            {{ row.prompt_tokens }} + {{ row.completion_tokens }} = <strong>{{ row.total_tokens }}</strong>
          </span>
          <span v-else class="text-muted">-</span>
        </template>
      </el-table-column>
      <el-table-column label="详情" min-width="200">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click="viewDetail(row)">查看</el-button>
          <span v-if="row.status === 'error'" class="error-hint">{{ row.error_message?.slice(0, 60) }}</span>
        </template>
      </el-table-column>
    </el-table>

    <div class="lark-pagination" v-if="total > 0">
      <el-pagination
        v-model:current-page="filter.page"
        v-model:page-size="filter.page_size"
        :page-sizes="[20, 50, 100]"
        :total="total"
        layout="total, sizes, prev, pager, next, jumper"
        @size-change="fetchLogs"
        @current-change="fetchLogs"
      />
    </div>

    <!-- 详情弹窗 -->
    <el-dialog v-model="detailVisible" title="AI 调用详情" width="700px" destroy-on-close>
      <el-descriptions :column="2" border size="default">
        <el-descriptions-item label="调用时间">{{ detail.called_at }}</el-descriptions-item>
        <el-descriptions-item label="模型">{{ detail.model }}</el-descriptions-item>
        <el-descriptions-item label="来源">{{ callerLabel(detail.caller) }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag size="small" :type="detail.status === 'success' ? 'success' : 'danger'">
            {{ detail.status === 'success' ? '成功' : '失败' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="耗时">{{ detail.duration_ms }}ms</el-descriptions-item>
        <el-descriptions-item label="Tokens">{{ detail.prompt_tokens }} + {{ detail.completion_tokens }} = {{ detail.total_tokens }}</el-descriptions-item>
      </el-descriptions>

      <div v-if="detail.error_message" class="detail-section">
        <div class="detail-label">错误信息</div>
        <pre class="detail-pre error-pre">{{ detail.error_message }}</pre>
      </div>

      <div v-if="detail.request_summary" class="detail-section">
        <div class="detail-label">请求摘要</div>
        <pre class="detail-pre">{{ detail.request_summary }}</pre>
      </div>

      <div v-if="detail.response_summary" class="detail-section">
        <div class="detail-label">响应摘要</div>
        <pre class="detail-pre">{{ detail.response_summary }}</pre>
      </div>

      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { getAiCallLogs } from '@/api/aiConfig'

const loading = ref(false)
const logs = ref([])
const total = ref(0)
const filter = reactive({ page: 1, page_size: 50, caller: '', status: '' })

const detailVisible = ref(false)
const detail = ref({})

const CALLER_MAP = {
  test_connection: '测试连接',
  parse_batch: '批量解析',
  parse_text: '文本解析',
  parse_image: '图片解析',
  parse_excel: '表格解析',
  reparse_with_hints: '二次解析',
  ai_order_parser: '订单解析',
}

function callerLabel(c) { return CALLER_MAP[c] || c || '-' }
function callerTagType(c) {
  if (c === 'test_connection') return 'info'
  if (c === 'reparse_with_hints') return 'warning'
  return 'info'
}

function handleSearch() {
  filter.page = 1
  fetchLogs()
}

async function fetchLogs() {
  loading.value = true
  try {
    const params = { page: filter.page, page_size: filter.page_size }
    if (filter.caller) params.caller = filter.caller
    if (filter.status) params.status = filter.status
    const res = await getAiCallLogs(params)
    const d = res.data || {}
    logs.value = d.list || []
    total.value = d.total || 0
  } catch {
    logs.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function viewDetail(row) {
  detail.value = { ...row }
  detailVisible.value = true
}

let notifyWs = null
let reconnectTimer = null

function connectNotifyWs() {
  if (notifyWs && notifyWs.readyState <= 1) return
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  notifyWs = new WebSocket(`${proto}://${location.host}/ws/notify`)
  notifyWs.onmessage = (evt) => {
    try {
      const msg = JSON.parse(evt.data)
      if (msg.event === 'new_ai_call_log') fetchLogs()
    } catch {}
  }
  notifyWs.onclose = () => {
    reconnectTimer = setTimeout(connectNotifyWs, 3000)
  }
  notifyWs.onerror = () => { notifyWs?.close() }
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
  fetchLogs()
  connectNotifyWs()
})

onUnmounted(() => {
  disconnectNotifyWs()
})
</script>

<style scoped>
.lark-ai-logs {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.logs-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.total-hint {
  font-size: 13px;
  color: var(--lark-text-secondary, #8f959e);
}

.token-text {
  font-size: 12px;
  color: var(--lark-text-secondary, #8f959e);
}

.token-text strong {
  color: var(--lark-text-primary, #1f2329);
}

.text-muted {
  color: var(--lark-text-tertiary, #bbb);
}

.error-hint {
  margin-left: 8px;
  font-size: 12px;
  color: #f56c6c;
}

.lark-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}

.detail-section {
  margin-top: 16px;
}

.detail-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--lark-text-primary, #1f2329);
  margin-bottom: 6px;
}

.detail-pre {
  background: var(--lark-bg-subtle, #f7f8fa);
  border-radius: 6px;
  padding: 12px;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 300px;
  overflow-y: auto;
  margin: 0;
}

.error-pre {
  color: #f56c6c;
  background: #fef0f0;
}

:deep(.el-table) {
  --el-table-border-color: var(--lark-border-light);
  --el-table-header-bg-color: var(--lark-bg-subtle);
  font-size: 13px;
}

:deep(.el-table td.el-table__cell) {
  padding: 6px 0;
}

:deep(.el-table th.el-table__cell) {
  font-weight: 600;
  color: var(--lark-text-primary);
}
</style>
