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
          <el-table-column label="订单号" prop="order_no" min-width="140" show-overflow-tooltip />
          <el-table-column label="纸张ID" prop="paper_id" min-width="170" show-overflow-tooltip />
          <el-table-column label="状态" width="100" align="center">
            <template #default="{ row }">
              <el-tag :type="statusTagType(row.scan_status)" size="small">{{ statusText(row.scan_status) }}</el-tag>
            </template>
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
                <el-tag size="small" effect="plain" style="margin-left:8px">纸张ID：{{ selectedRecord.paper_id || '-' }}</el-tag>
              </div>
            </div>
          </div>

          <div class="detail-grid">
            <div class="detail-block">
              <div class="block-title">基础信息</div>
              <div class="summary-grid">
                <div class="summary-item">
                  <span class="summary-label">订单号</span>
                  <strong class="summary-value">{{ selectedRecord.order_no || '-' }}</strong>
                </div>
                <div class="summary-item">
                  <span class="summary-label">纸张ID</span>
                  <strong class="summary-value">{{ selectedRecord.paper_id || '-' }}</strong>
                </div>
                <div class="summary-item">
                  <span class="summary-label">审核状态</span>
                  <strong class="summary-value">{{ statusText(selectedRecord.scan_status) }}</strong>
                </div>
                <div class="summary-item">
                  <span class="summary-label">识别来源</span>
                  <strong class="summary-value">{{ sourceText(selectedRecord.code_source) }}</strong>
                </div>
                <div class="summary-item">
                  <span class="summary-label">扫码时间</span>
                  <strong class="summary-value">{{ formatDate(selectedRecord.created_at) }}</strong>
                </div>
              </div>
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
              <div class="summary-grid summary-grid-compact">
                <div class="summary-item" v-if="selectedRecord.fallback_ocr.order_no">
                  <span class="summary-label">识别订单号</span>
                  <strong class="summary-value">{{ selectedRecord.fallback_ocr.order_no }}</strong>
                </div>
                <div class="summary-item" v-if="selectedRecord.fallback_ocr.paper_id">
                  <span class="summary-label">识别纸张ID</span>
                  <strong class="summary-value">{{ selectedRecord.fallback_ocr.paper_id }}</strong>
                </div>
                <div class="summary-item" v-if="selectedRecord.fallback_ocr.confidence !== undefined && selectedRecord.fallback_ocr.confidence !== null">
                  <span class="summary-label">置信度</span>
                  <strong class="summary-value">{{ selectedRecord.fallback_ocr.confidence }}</strong>
                </div>
              </div>
              <pre v-if="selectedRecord.fallback_ocr.combined_text" class="json-block">{{ selectedRecord.fallback_ocr.combined_text }}</pre>
            </div>

            <div class="detail-block" v-if="selectedRecord.ai_parsed">
              <div class="block-title">表格 AI 解析结果</div>
              <el-table v-if="parsedTableRows.length" :data="parsedTableRows" border size="small" class="parsed-table">
                <el-table-column type="index" label="序" width="48" align="center" />
                <el-table-column label="款号" prop="product_no" min-width="110" align="center" header-align="center" />
                <el-table-column label="颜色" prop="color" min-width="100" align="center" header-align="center" />
                <el-table-column v-for="size in parsedSizeColumns" :key="size" :label="size" width="68" align="center" header-align="center">
                  <template #default="{ row }">
                    {{ row.sizeMap[size] || '' }}
                  </template>
                </el-table-column>
                <el-table-column label="合计" width="72" align="center" header-align="center">
                  <template #default="{ row }">
                    <span class="table-total">{{ row.total }}</span>
                  </template>
                </el-table-column>
              </el-table>
              <el-empty v-else description="暂无解析明细" :image-size="44" />
              <pre v-if="selectedRecord.ai_parsed.remark" class="json-block">{{ selectedRecord.ai_parsed.remark }}</pre>
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
import { computed, onMounted, reactive, ref } from 'vue'
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

const preferredSizeOrder = ['XS', 'S', 'M', 'L', 'XL', '2XL', '3XL', '4XL', '5XL', '6XL']

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

const parsedTableRows = computed(() => {
  const items = selectedRecord.value?.ai_parsed?.items
  if (!Array.isArray(items)) return []
  return items.map((item, index) => {
    const sizeMap = item?.sizes && typeof item.sizes === 'object' ? item.sizes : {}
    const total = Object.values(sizeMap).reduce((sum, qty) => sum + (Number(qty) || 0), 0)
    return {
      id: `${selectedRecord.value?.id || 'record'}-${index}`,
      product_no: item?.product_no || '',
      color: item?.color || '',
      sizeMap,
      total
    }
  })
})

const parsedSizeColumns = computed(() => {
  const sizeSet = new Set()
  parsedTableRows.value.forEach(row => {
    Object.keys(row.sizeMap || {}).forEach(size => {
      if (size) sizeSet.add(String(size))
    })
  })
  return Array.from(sizeSet).sort((a, b) => {
    const ia = preferredSizeOrder.indexOf(a)
    const ib = preferredSizeOrder.indexOf(b)
    if (ia !== -1 && ib !== -1) return ia - ib
    if (ia !== -1) return -1
    if (ib !== -1) return 1
    return a.localeCompare(b)
  })
})

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
  grid-template-columns: 360px 1fr;
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

.summary-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.summary-grid-compact {
  margin-bottom: 12px;
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px;
  background: #fafafa;
  border-radius: 6px;
}

.summary-label {
  font-size: 12px;
  color: #909399;
}

.summary-value {
  color: #303133;
  word-break: break-all;
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

.parsed-table {
  width: 100%;
}

.table-total {
  font-weight: 600;
  color: #1f2329;
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
