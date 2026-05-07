<template>
  <div class="lark-scan-records">
    <div class="lark-page-header">
      <div class="header-title">发货单识别</div>
      <div class="header-desc">查看发货群扫码识别记录、AI 解析结果与发货单创建状态</div>
    </div>

    <div class="lark-table-panel">
      <div class="lark-toolbar">
        <div class="toolbar-left">
          <el-input v-model="filters.order_no" placeholder="搜索订单号" clearable style="width: 220px" @keyup.enter="handleSearch" />
          <el-select v-model="filters.scan_status" placeholder="识别状态" clearable style="width: 140px" @change="handleSearch">
            <el-option label="全部状态" value="" />
            <el-option label="成功" value="success" />
            <el-option label="失败" value="failed" />
            <el-option label="处理中" value="pending" />
            <el-option label="待审核" value="review_pending" />
            <el-option label="已作废" value="voided" />
          </el-select>
          <el-button type="primary" @click="handleSearch">查询</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </div>
        <div class="toolbar-right">
          <el-button type="warning" plain @click="goToReviewPage">待审核页面</el-button>
          <el-button @click="fetchStats">刷新统计</el-button>
        </div>
      </div>

      <div class="summary-bar" v-if="pagination.total > 0">
        <span class="summary-item">共 <strong>{{ pagination.total }}</strong> 条</span>
        <span class="summary-item">成功 <strong>{{ stats.success_count || 0 }}</strong> 条</span>
        <span class="summary-item">失败 <strong>{{ stats.failed_count || 0 }}</strong> 条</span>
        <span class="summary-item">处理中 <strong>{{ stats.pending_count || 0 }}</strong> 条</span>
        <span class="summary-item">待审核 <strong>{{ stats.review_pending_count || 0 }}</strong> 条</span>
      </div>

      <el-table :data="tableData" v-loading="loading" stripe class="lark-table" highlight-current-row @row-click="onRowClick">
        <el-table-column label="图片" width="90" align="center">
          <template #default="{ row }">
            <div class="thumb-wrap" v-if="row.msg_log_id && row.image_oss_key" @click.stop="previewImage(row)">
              <img :src="mediaUrl(row.msg_log_id)" class="thumb-img" loading="lazy" />
            </div>
            <span v-else class="text-muted">无图</span>
          </template>
        </el-table-column>
        <el-table-column label="订单号" prop="order_no" min-width="130">
          <template #default="{ row }">
            <span v-if="row.order_no" class="link-text" @click.stop="goToOrder(row.order_no)">{{ row.order_no }}</span>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.scan_status)" size="small">{{ statusText(row.scan_status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="识别来源" width="100" align="center">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ sourceText(row.code_source) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="发货单号" prop="shipment_no" min-width="130">
          <template #default="{ row }">
            <span v-if="row.shipment_no">{{ row.shipment_no }}</span>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="纸张ID" prop="paper_id" min-width="120" show-overflow-tooltip />
        <el-table-column label="扫码人" prop="scanner_name" width="100">
          <template #default="{ row }">
            {{ row.scanner_name || row.sender_id || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="群名" prop="room_name" min-width="120" show-overflow-tooltip />
        <el-table-column label="错误信息" prop="error_message" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.error_message" class="error-text">{{ row.error_message }}</span>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="时间" width="170">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>
      </el-table>

      <div class="lark-pagination">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :total="pagination.total"
          :page-sizes="[20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          @current-change="fetchData"
          @size-change="handleSearch"
        />
      </div>
    </div>

    <!-- 图片预览 -->
    <el-image-viewer
      v-if="previewUrl"
      :url-list="[previewUrl]"
      :initial-index="0"
      @close="previewUrl = ''"
      teleported
    />

    <!-- 详情抽屉 -->
    <el-drawer v-model="drawerVisible" title="识别详情" size="520px" direction="rtl">
      <template v-if="selectedRecord">
        <div class="detail-section">
          <div class="detail-row">
            <span class="detail-label">订单号</span>
            <span class="detail-value link-text" v-if="selectedRecord.order_no" @click="goToOrder(selectedRecord.order_no)">{{ selectedRecord.order_no }}</span>
            <span class="detail-value" v-else>-</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">状态</span>
            <el-tag :type="statusTagType(selectedRecord.scan_status)" size="small">{{ statusText(selectedRecord.scan_status) }}</el-tag>
          </div>
          <div class="detail-row">
            <span class="detail-label">识别来源</span>
            <span class="detail-value">{{ sourceText(selectedRecord.code_source) }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">发货单号</span>
            <span class="detail-value">{{ selectedRecord.shipment_no || '-' }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">纸张ID</span>
            <span class="detail-value" style="word-break:break-all">{{ selectedRecord.paper_id || '-' }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">扫码人</span>
            <span class="detail-value">{{ selectedRecord.scanner_name || selectedRecord.sender_id || '-' }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">群名</span>
            <span class="detail-value">{{ selectedRecord.room_name || '-' }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">时间</span>
            <span class="detail-value">{{ formatDate(selectedRecord.created_at) }}</span>
          </div>
          <div class="detail-row" v-if="selectedRecord.error_message">
            <span class="detail-label">错误信息</span>
            <span class="detail-value" style="color:#f56c6c">{{ selectedRecord.error_message }}</span>
          </div>
        </div>

        <el-divider>扫码图片</el-divider>
        <div class="detail-image" v-if="selectedRecord.msg_log_id && selectedRecord.image_oss_key">
          <img :src="mediaUrl(selectedRecord.msg_log_id)" class="detail-img" @click="previewImage(selectedRecord)" />
        </div>
        <div v-else style="color:#c0c4cc;text-align:center;padding:20px">无图片</div>

        <el-divider v-if="selectedRecord.ai_parsed">AI 识别结果</el-divider>
        <div v-if="selectedRecord.ai_parsed" class="ai-result-block">
          <pre class="ai-json">{{ JSON.stringify(selectedRecord.ai_parsed, null, 2) }}</pre>
        </div>

        <el-divider v-if="selectedRecord.fallback_ocr">码下文字兜底识别</el-divider>
        <div v-if="selectedRecord.fallback_ocr" class="ai-result-block">
          <pre class="ai-json">{{ JSON.stringify(selectedRecord.fallback_ocr, null, 2) }}</pre>
        </div>

        <el-divider v-if="selectedRecord.qr_content">二维码内容</el-divider>
        <div v-if="selectedRecord.qr_content" class="qr-content-block">
          <code>{{ selectedRecord.qr_content }}</code>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElImageViewer } from 'element-plus'
import { getScanRecords, getScanStats } from '@/api/shippingScans'

const router = useRouter()
const loading = ref(false)
const tableData = ref([])
const stats = ref({})
const previewUrl = ref('')
const drawerVisible = ref(false)
const selectedRecord = ref(null)

const filters = reactive({
  order_no: '',
  scan_status: ''
})

const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
})

const mediaUrl = (msgLogId) => {
  const t = localStorage.getItem('token') || ''
  return `/api/downstream-orders/media/${msgLogId}?token=${encodeURIComponent(t)}`
}

const handleSearch = () => {
  pagination.page = 1
  fetchData()
}

const fetchData = async () => {
  loading.value = true
  try {
    const res = await getScanRecords({
      page: pagination.page,
      pageSize: pagination.pageSize,
      scan_status: filters.scan_status || undefined,
      order_no: filters.order_no || undefined
    })
    const d = res.data || {}
    tableData.value = d.list || []
    pagination.total = d.total || 0
  } finally {
    loading.value = false
  }
}

const fetchStats = async () => {
  try {
    const res = await getScanStats()
    stats.value = res.data || {}
  } catch (e) { /* ignore */ }
}

const goToReviewPage = () => {
  router.push('/shipping-scan-reviews')
}

const resetFilters = () => {
  filters.order_no = ''
  filters.scan_status = ''
  pagination.page = 1
  fetchData()
}

const statusText = (s) => {
  const map = { success: '成功', failed: '失败', pending: '处理中', parsing: '处理中', review_pending: '待审核', voided: '已作废' }
  return map[s] || s || '-'
}

const statusTagType = (s) => {
  const map = { success: 'success', failed: 'danger', pending: 'warning', parsing: 'warning', review_pending: 'info', voided: 'info' }
  return map[s] || 'info'
}

const sourceText = (v) => {
  const map = { gridcode: '方块码', ai_text: '右上角识别智能体', ai_agent: '右上角识别智能体' }
  return map[v] || (v || '-')
}

const formatDate = (v) => {
  if (!v) return '-'
  return String(v).replace('T', ' ').slice(0, 19)
}

const previewImage = (row) => {
  if (row.msg_log_id && row.image_oss_key) {
    previewUrl.value = mediaUrl(row.msg_log_id)
  }
}

const onRowClick = (row) => {
  selectedRecord.value = row
  drawerVisible.value = true
}

const goToOrder = (orderNo) => {
  if (orderNo) router.push(`/sales/${encodeURIComponent(orderNo)}`)
}

onMounted(() => {
  fetchData()
  fetchStats()
})
</script>

<style scoped>
.lark-scan-records {
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: 100%;
}

.lark-page-header {
  flex-shrink: 0;
}

.header-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--lark-text-primary, #1f2329);
}

.header-desc {
  font-size: 13px;
  color: var(--lark-text-secondary, #646a73);
  margin-top: 4px;
}

.lark-table-panel {
  background: var(--lark-bg-base, #fff);
  border-radius: var(--lark-radius-lg, 8px);
  padding: 20px;
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.lark-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
  flex-shrink: 0;
}

.toolbar-left {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

.toolbar-right {
  display: flex;
  gap: 8px;
  align-items: center;
}

.summary-bar {
  font-size: 12px;
  color: var(--lark-text-secondary, #646a73);
  margin-bottom: 10px;
  display: flex;
  gap: 18px;
  flex-shrink: 0;
  flex-wrap: wrap;
}

.summary-bar strong {
  color: var(--lark-text-primary, #1f2329);
}

.lark-table {
  flex: 1;
  min-height: 0;
}

.thumb-wrap {
  width: 60px;
  height: 60px;
  overflow: hidden;
  border-radius: 4px;
  cursor: pointer;
  border: 1px solid #ebeef5;
  display: flex;
  align-items: center;
  justify-content: center;
}
.thumb-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.thumb-wrap:hover {
  border-color: #409eff;
}

.link-text {
  color: #409eff;
  cursor: pointer;
}
.link-text:hover {
  text-decoration: underline;
}

.text-muted {
  color: #c0c4cc;
}

.error-text {
  color: #f56c6c;
}

.lark-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
  flex-shrink: 0;
}

.detail-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.detail-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}
.detail-label {
  min-width: 72px;
  font-weight: 600;
  color: #606266;
  flex-shrink: 0;
}
.detail-value {
  color: #303133;
  word-break: break-all;
}

.detail-image {
  text-align: center;
}
.detail-img {
  max-width: 100%;
  max-height: 400px;
  border-radius: 6px;
  cursor: pointer;
  border: 1px solid #ebeef5;
}
.detail-img:hover {
  border-color: #409eff;
}

.ai-result-block {
  background: #fafafa;
  border-radius: 6px;
  padding: 12px;
  overflow: auto;
  max-height: 300px;
}
.ai-json {
  font-size: 12px;
  font-family: 'Consolas', 'Monaco', monospace;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
  color: #303133;
}

.qr-content-block {
  background: #fafafa;
  border-radius: 6px;
  padding: 12px;
  word-break: break-all;
}
.qr-content-block code {
  font-size: 12px;
  color: #606266;
}
</style>
