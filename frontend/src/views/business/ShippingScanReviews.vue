<template>
  <div class="shipping-review-page">
    <div class="lark-page-header">
      <div class="header-title">发货单审核</div>
      <div class="header-desc">审核触发 AI 码下文字兜底的发货单识别记录，确认后再下发货单</div>
    </div>

    <div class="review-layout">
      <div class="review-list-panel">
        <div class="panel-toolbar">
          <div class="toolbar-left">
            <el-input v-model="filters.order_no" placeholder="搜索订单号" clearable style="width: 220px" @keyup.enter="handleSearch" />
            <el-select v-model="filters.scan_status" placeholder="状态" style="width: 140px" @change="handleSearch">
              <el-option label="待审核" value="review_pending" />
              <el-option label="已作废" value="voided" />
              <el-option label="已成功" value="success" />
            </el-select>
            <el-button type="primary" @click="handleSearch">查询</el-button>
            <el-button @click="resetFilters">重置</el-button>
          </div>
        </div>

        <el-table
          :data="tableData"
          v-loading="loading"
          height="100%"
          highlight-current-row
          @current-change="handleCurrentChange"
        >
          <el-table-column label="订单号" prop="order_no" min-width="130" show-overflow-tooltip />
          <el-table-column label="状态" width="100" align="center">
            <template #default="{ row }">
              <el-tag :type="statusTagType(row.scan_status)" size="small">{{ statusText(row.scan_status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="来源" width="100" align="center">
            <template #default="{ row }">
              <el-tag size="small" effect="plain">{{ sourceText(row.code_source) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="纸张ID" prop="paper_id" min-width="150" show-overflow-tooltip />
          <el-table-column label="时间" width="170">
            <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
          </el-table-column>
        </el-table>

        <div class="list-footer">
          <el-pagination
            v-model:current-page="pagination.page"
            v-model:page-size="pagination.pageSize"
            :total="pagination.total"
            :page-sizes="[20, 50, 100]"
            layout="total, sizes, prev, pager, next"
            @current-change="fetchData"
            @size-change="handleSearch"
          />
        </div>
      </div>

      <div class="review-detail-panel">
        <template v-if="selectedRecord">
          <div class="detail-header-row">
            <div>
              <div class="detail-title">{{ selectedRecord.order_no || '未识别订单号' }}</div>
              <div class="detail-subtitle">
                <el-tag :type="statusTagType(selectedRecord.scan_status)" size="small">{{ statusText(selectedRecord.scan_status) }}</el-tag>
                <el-tag size="small" effect="plain" style="margin-left:8px">{{ sourceText(selectedRecord.code_source) }}</el-tag>
              </div>
            </div>
          </div>

          <div class="detail-grid">
            <div class="detail-block">
              <div class="block-title">基础信息</div>
              <div class="info-row"><span>纸张ID</span><strong>{{ selectedRecord.paper_id || '-' }}</strong></div>
              <div class="info-row"><span>扫码人</span><strong>{{ selectedRecord.scanner_name || selectedRecord.sender_id || '-' }}</strong></div>
              <div class="info-row"><span>群名</span><strong>{{ selectedRecord.room_name || '-' }}</strong></div>
              <div class="info-row"><span>时间</span><strong>{{ formatDate(selectedRecord.created_at) }}</strong></div>
              <div class="info-row" v-if="selectedRecord.error_message"><span>提示</span><strong class="danger-text">{{ selectedRecord.error_message }}</strong></div>
            </div>

            <div class="detail-block">
              <div class="block-title">扫码图片</div>
              <div class="image-wrap" v-if="selectedRecord.msg_log_id && selectedRecord.image_oss_key">
                <img :src="mediaUrl(selectedRecord.msg_log_id)" class="detail-img" @click="previewImage(selectedRecord)" />
              </div>
              <el-empty v-else description="无图片" :image-size="44" />
            </div>

            <div class="detail-block" v-if="selectedRecord.fallback_ocr">
              <div class="block-title">码下文字兜底识别</div>
              <pre class="json-block">{{ JSON.stringify(selectedRecord.fallback_ocr, null, 2) }}</pre>
            </div>

            <div class="detail-block" v-if="selectedRecord.ai_parsed">
              <div class="block-title">表格 AI 解析结果</div>
              <pre class="json-block">{{ JSON.stringify(selectedRecord.ai_parsed, null, 2) }}</pre>
            </div>

            <div class="detail-block" v-if="selectedRecord.qr_content">
              <div class="block-title">码内容</div>
              <pre class="json-block">{{ selectedRecord.qr_content }}</pre>
            </div>
          </div>

          <div class="review-actions">
            <el-input v-model="reviewNote" placeholder="审核备注（选填）" clearable />
            <div class="action-buttons" v-if="selectedRecord.scan_status === 'review_pending'">
              <el-button type="primary" :loading="actionLoading" @click="handleApprove">审核通过并下发货单</el-button>
              <el-button type="danger" plain :loading="actionLoading" @click="handleVoid">作废</el-button>
            </div>
          </div>
        </template>
        <div v-else class="empty-detail">
          <el-empty description="请选择一条发货单识别记录" />
        </div>
      </div>
    </div>

    <el-image-viewer
      v-if="previewUrl"
      :url-list="[previewUrl]"
      :initial-index="0"
      @close="previewUrl = ''"
      teleported
    />
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElImageViewer, ElMessage, ElMessageBox } from 'element-plus'
import { approveScanRecord, getScanRecords, voidScanRecord } from '@/api/shippingScans'

const loading = ref(false)
const actionLoading = ref(false)
const tableData = ref([])
const selectedRecord = ref(null)
const reviewNote = ref('')
const previewUrl = ref('')

const filters = reactive({
  order_no: '',
  scan_status: 'review_pending'
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

const handleCurrentChange = (row) => {
  selectedRecord.value = row || null
  reviewNote.value = row?.review_note || ''
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
    const data = res.data || {}
    tableData.value = data.list || []
    pagination.total = data.total || 0
    if (tableData.value.length === 0) {
      selectedRecord.value = null
      reviewNote.value = ''
      return
    }
    const currentId = selectedRecord.value?.id
    selectedRecord.value = tableData.value.find(item => item.id === currentId) || tableData.value[0]
    reviewNote.value = selectedRecord.value?.review_note || ''
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  pagination.page = 1
  fetchData()
}

const resetFilters = () => {
  filters.order_no = ''
  filters.scan_status = 'review_pending'
  handleSearch()
}

const previewImage = (row) => {
  if (row?.msg_log_id && row?.image_oss_key) {
    previewUrl.value = mediaUrl(row.msg_log_id)
  }
}

const handleApprove = async () => {
  if (!selectedRecord.value) return
  await ElMessageBox.confirm('确认审核通过并创建销售发货单吗？', '审核确认', {
    confirmButtonText: '确认',
    cancelButtonText: '取消',
    type: 'warning'
  })
  actionLoading.value = true
  try {
    const res = await approveScanRecord(selectedRecord.value.id, { review_note: reviewNote.value })
    const data = res.data || {}
    ElMessage.success(`审核成功，发货单号：${data.shipment_no || '-'}`)
    await fetchData()
  } finally {
    actionLoading.value = false
  }
}

const handleVoid = async () => {
  if (!selectedRecord.value) return
  await ElMessageBox.confirm('确认作废这条发货单识别记录吗？', '作废确认', {
    confirmButtonText: '确认',
    cancelButtonText: '取消',
    type: 'warning'
  })
  actionLoading.value = true
  try {
    await voidScanRecord(selectedRecord.value.id, { review_note: reviewNote.value })
    ElMessage.success('已作废')
    await fetchData()
  } finally {
    actionLoading.value = false
  }
}

onMounted(() => {
  fetchData()
})
</script>

<style scoped>
.shipping-review-page {
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

.review-layout {
  display: grid;
  grid-template-columns: 420px 1fr;
  gap: 16px;
  min-height: 0;
  flex: 1;
}

.review-list-panel,
.review-detail-panel {
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.panel-toolbar,
.list-footer,
.review-actions {
  flex-shrink: 0;
}

.toolbar-left {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.review-detail-panel {
  gap: 14px;
  overflow: auto;
}

.detail-title {
  font-size: 20px;
  font-weight: 600;
}

.detail-subtitle {
  margin-top: 8px;
}

.detail-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.detail-block {
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 12px;
}

.block-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 10px;
}

.info-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.info-row span {
  color: #606266;
}

.info-row strong {
  color: #303133;
  word-break: break-all;
  text-align: right;
}

.image-wrap {
  text-align: center;
}

.detail-img {
  max-width: 100%;
  max-height: 360px;
  border-radius: 6px;
  cursor: pointer;
  border: 1px solid #ebeef5;
}

.json-block {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
  font-size: 12px;
  line-height: 1.6;
  color: #303133;
  background: #fafafa;
  border-radius: 6px;
  padding: 12px;
}

.review-actions {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.action-buttons {
  display: flex;
  gap: 10px;
}

.danger-text {
  color: #f56c6c;
}

.empty-detail {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.list-footer {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
</style>
