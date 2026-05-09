<template>
  <div class="review-page">
    <div class="review-main">
      <div class="detail-panel">
        <div class="detail-header">
          <div class="detail-header-left">
            <el-button :disabled="!hasPrev" @click="goPrev" size="default">&laquo; 上一条</el-button>
            <span class="nav-index">{{ currentAbsoluteIndex }} / {{ pagination.total }}</span>
            <el-button :disabled="!hasNext" @click="goNext" size="default">下一条 &raquo;</el-button>
            <el-divider direction="vertical" />
            <span class="detail-room">{{ selectedRecord?.order_no || '暂无记录' }}</span>
            <span class="detail-sender">/ 纸张ID {{ selectedRecord?.paper_id || '-' }}</span>
            <el-tag v-if="selectedRecord" size="small" :type="statusTagType(selectedRecord.scan_status)" style="margin-left:8px">{{ statusText(selectedRecord.scan_status) }}</el-tag>
            <el-tag v-if="selectedRecord" size="small" type="info" style="margin-left:4px">{{ sourceText(selectedRecord.code_source) }}</el-tag>
            <span v-if="selectedRecord?.shipment_no" class="detail-uid">{{ selectedRecord.shipment_no }}</span>
          </div>
          <div class="detail-header-right">
            <el-input v-model="filters.order_no" placeholder="搜索订单号" clearable style="width: 180px" @clear="handleSearch" @keyup.enter="handleSearch" />
            <el-select v-model="filters.scan_status" size="default" style="width: 130px" @change="handleSearch">
              <el-option label="待审核" value="review_pending" />
              <el-option label="已作废" value="voided" />
              <el-option label="已成功" value="success" />
            </el-select>
            <el-button type="primary" @click="handleSearch">查询</el-button>
            <el-button @click="resetFilters">重置</el-button>
          </div>
        </div>

        <template v-if="selectedRecord">

          <div class="detail-body">
            <div class="compare-grid">
              <div class="compare-left">
                <el-tabs v-model="leftTab" class="left-tabs">
                  <el-tab-pane label="信息来源" name="source">
                    <div class="source-panel">
                      <div v-if="sourceImageUrl" class="source-img-viewport">
                        <img :src="sourceImageUrl" class="source-preview-img" @click="previewImage(sourceImageUrl)" />
                      </div>
                      <el-empty v-else description="暂无来源图片" :image-size="48" />
                    </div>
                  </el-tab-pane>
                  <el-tab-pane label="识别辅助" name="aux">
                    <div class="uncertain-panel">
                      <template v-if="hasAuxInfo">
                        <div class="aux-grid" v-if="selectedRecord.fallback_ocr">
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
                        <pre v-if="selectedRecord.fallback_ocr?.combined_text" class="json-block">{{ selectedRecord.fallback_ocr.combined_text }}</pre>
                        <pre v-if="selectedRecord.qr_content" class="json-block">{{ selectedRecord.qr_content }}</pre>
                        <div v-if="selectedRecord.error_message" class="uncertain-item">{{ selectedRecord.error_message }}</div>
                      </template>
                      <el-empty v-else description="暂无辅助信息" :image-size="48" />
                    </div>
                  </el-tab-pane>
                </el-tabs>
              </div>

              <el-image-viewer
                v-if="previewUrl"
                :url-list="[previewUrl]"
                :initial-index="0"
                @close="previewUrl = ''"
                teleported
              />

              <div class="compare-right">
                <div class="panel-label">解析结果（下发货内容）</div>
                <div class="order-info-bar">
                  <span>订单号：{{ selectedRecord.order_no || '-' }}</span>
                  <span>纸张ID：{{ selectedRecord.paper_id || '-' }}</span>
                  <span>识别来源：{{ sourceText(selectedRecord.code_source) }}</span>
                  <span>扫码时间：{{ formatDate(selectedRecord.created_at) }}</span>
                </div>
                <div class="edit-form-area">
                  <el-table v-if="parsedTableRows.length" :data="parsedTableRows" border size="small" class="order-table">
                    <el-table-column type="index" label="序" width="40" align="center" />
                    <el-table-column label="款号" prop="product_no" min-width="90" align="center" header-align="center" />
                    <el-table-column label="颜色" prop="color" min-width="80" align="center" header-align="center" />
                    <el-table-column v-for="size in parsedSizeColumns" :key="size" :label="size" width="58" align="center" class-name="size-col">
                      <template #default="{ row }">
                        {{ row.sizeMap[size] || '' }}
                      </template>
                    </el-table-column>
                    <el-table-column label="合计" width="54" align="center" class-name="total-col">
                      <template #default="{ row }">
                        <span class="cell-total">{{ row.total }}</span>
                      </template>
                    </el-table-column>
                  </el-table>
                  <el-empty v-else description="暂无解析明细" :image-size="48" />
                  <pre v-if="selectedRecord.ai_parsed?.remark" class="json-block parsed-remark">{{ selectedRecord.ai_parsed.remark }}</pre>
                </div>
              </div>
            </div>
          </div>

          <div class="detail-footer">
            <div class="footer-form">
              <el-input v-model="reviewNote" placeholder="审核备注（选填）" style="flex:1" />
            </div>
            <div class="footer-actions">
              <template v-if="selectedRecord.scan_status === 'review_pending'">
                <el-button type="primary" :loading="actionLoading" @click="handleApprove">审核通过并下发货单</el-button>
                <el-button type="danger" plain :loading="actionLoading" @click="handleVoid">作废</el-button>
              </template>
            </div>
          </div>
        </template>
        <el-empty v-else :description="loading ? '加载中...' : '暂无待审核数据'" class="detail-empty" />
      </div>
    </div>
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
const leftTab = ref('source')

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

const currentIndex = computed(() => {
  if (!selectedRecord.value) return -1
  return tableData.value.findIndex(item => item.id === selectedRecord.value.id)
})

const currentAbsoluteIndex = computed(() => {
  if (currentIndex.value < 0) return 0
  return (pagination.page - 1) * pagination.pageSize + currentIndex.value + 1
})

const hasPrev = computed(() => {
  if (!selectedRecord.value) return false
  return currentIndex.value > 0 || pagination.page > 1
})

const hasNext = computed(() => {
  if (!selectedRecord.value || currentIndex.value < 0) return false
  if (currentIndex.value < tableData.value.length - 1) return true
  return pagination.page * pagination.pageSize < pagination.total
})

const sourceImageUrl = computed(() => {
  const row = selectedRecord.value
  if (!row?.msg_log_id || !row?.image_oss_key) return ''
  return mediaUrl(row.msg_log_id)
})

const hasAuxInfo = computed(() => {
  const row = selectedRecord.value
  return !!(row?.fallback_ocr || row?.qr_content || row?.error_message)
})

const handleCurrentChange = (row) => {
  selectedRecord.value = row || null
  reviewNote.value = row?.review_note || ''
}

const fetchData = async (options = {}) => {
  const targetPage = options.page || pagination.page
  loading.value = true
  try {
    const res = await getScanRecords({
      page: targetPage,
      pageSize: pagination.pageSize,
      scan_status: filters.scan_status || undefined,
      order_no: filters.order_no || undefined
    })
    const data = res.data || {}
    const rows = data.list || []
    tableData.value = rows
    pagination.page = targetPage
    pagination.total = data.total || 0

    if (!rows.length) {
      if (targetPage > 1 && pagination.total > 0) {
        return await fetchData({ ...options, page: targetPage - 1, selectStrategy: 'last' })
      }
      selectedRecord.value = null
      reviewNote.value = ''
      return null
    }

    let nextRow = null
    if (options.selectId) {
      nextRow = rows.find(item => item.id === options.selectId) || null
    }
    if (!nextRow && options.selectStrategy === 'last') {
      nextRow = rows[rows.length - 1]
    }
    if (!nextRow && options.selectStrategy === 'first') {
      nextRow = rows[0]
    }
    if (!nextRow) {
      const currentId = selectedRecord.value?.id
      nextRow = rows.find(item => item.id === currentId) || rows[0]
    }

    handleCurrentChange(nextRow)
    return nextRow
  } finally {
    loading.value = false
  }
}

const handleSearch = async () => {
  pagination.page = 1
  await fetchData({ page: 1, selectStrategy: 'first' })
}

const resetFilters = async () => {
  filters.order_no = ''
  filters.scan_status = 'review_pending'
  await handleSearch()
}

const goPrev = async () => {
  if (!hasPrev.value) return
  if (currentIndex.value > 0) {
    handleCurrentChange(tableData.value[currentIndex.value - 1])
    return
  }
  if (pagination.page > 1) {
    await fetchData({ page: pagination.page - 1, selectStrategy: 'last' })
  }
}

const goNext = async () => {
  if (!hasNext.value) return
  if (currentIndex.value < tableData.value.length - 1) {
    handleCurrentChange(tableData.value[currentIndex.value + 1])
    return
  }
  if (pagination.page * pagination.pageSize < pagination.total) {
    await fetchData({ page: pagination.page + 1, selectStrategy: 'first' })
  }
}

const previewImage = (url) => {
  if (url) previewUrl.value = url
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
    await fetchData({ page: pagination.page, selectStrategy: 'first' })
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
    await fetchData({ page: pagination.page, selectStrategy: 'first' })
  } finally {
    actionLoading.value = false
  }
}

onMounted(() => {
  fetchData({ page: 1, selectStrategy: 'first' })
})
</script>

<style scoped>
.review-page {
  height: calc(100vh - 100px);
  display: flex;
  flex-direction: column;
}

.review-main {
  flex: 1;
  display: flex;
  gap: 16px;
  min-height: 0;
}

.nav-index {
  font-size: 13px;
  color: var(--lark-text-secondary);
  min-width: 72px;
  text-align: center;
}

.detail-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.detail-panel {
  flex: 1;
  min-width: 0;
  background: var(--lark-bg-base);
  border-radius: var(--lark-radius-lg);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.detail-empty {
  margin: auto;
}

.detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  border-bottom: 1px solid var(--lark-border-light);
  flex-shrink: 0;
}

.detail-header-left {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.detail-room {
  font-size: 15px;
  font-weight: 600;
  color: var(--lark-text-primary);
  white-space: nowrap;
}

.detail-sender {
  font-size: 13px;
  color: var(--lark-text-secondary);
  white-space: nowrap;
}

.detail-uid {
  font-size: 12px;
  color: #909399;
  font-family: 'Courier New', monospace;
  margin-left: 8px;
  background: #f4f4f5;
  padding: 1px 6px;
  border-radius: 3px;
}

.detail-body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  padding: 16px 20px;
}

.compare-grid {
  display: grid;
  grid-template-columns: 470px 1fr;
  gap: 16px;
  height: 100%;
}

.compare-left,
.compare-right {
  display: flex;
  flex-direction: column;
}

.compare-left {
  border-right: 1px solid var(--lark-border-light);
  padding-right: 16px;
  overflow-y: auto;
  overflow-x: hidden;
  min-height: 0;
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.compare-left::-webkit-scrollbar {
  display: none;
}

.compare-right {
  overflow-y: auto;
  min-height: 0;
  scrollbar-width: none;
  -ms-overflow-style: none;
  padding: 0 4px;
}

.compare-right::-webkit-scrollbar {
  display: none;
}

.panel-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--lark-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 10px;
  position: sticky;
  top: 0;
  z-index: 1;
  padding: 4px 0;
  background: var(--lark-bg-base, #fff);
}

.left-tabs {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.left-tabs :deep(.el-tabs__header) {
  margin-bottom: 0;
  flex-shrink: 0;
}

.left-tabs :deep(.el-tabs__content) {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.left-tabs :deep(.el-tabs__content)::-webkit-scrollbar {
  display: none;
}

.left-tabs :deep(.el-tab-pane) {
  height: 100%;
}

.source-panel {
  padding: 0;
  height: 100%;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.source-img-viewport {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}

.source-preview-img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  border-radius: 4px;
  cursor: pointer;
}

.uncertain-panel {
  padding: 12px 10px;
  height: 100%;
  overflow-y: auto;
}

.uncertain-item {
  font-size: 13px;
  color: #8c6d1f;
  background: #fffbe6;
  border: 1px solid #ffe58f;
  border-radius: 6px;
  padding: 8px 12px;
  margin-top: 10px;
  line-height: 1.5;
  word-break: break-word;
}

.aux-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 10px;
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

.json-block + .json-block {
  margin-top: 10px;
}

.order-info-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  font-size: 13px;
  color: var(--lark-text-regular);
  margin-bottom: 12px;
}

.edit-form-area {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.order-table {
  margin-bottom: 0;
  flex: 1;
  min-height: 0;
}

.order-table :deep(.el-table__header-wrapper th.el-table__cell) {
  padding: 6px 0 !important;
  height: 36px;
  background: #fafafa;
  font-weight: 600;
  font-size: 12px;
  color: #606266;
}

.order-table :deep(.el-table__body-wrapper) {
  flex: 1;
  min-height: 0;
}

.order-table :deep(.el-table__cell) {
  padding: 0 !important;
  height: 32px;
}

.order-table :deep(.cell) {
  padding: 0 !important;
  line-height: 32px;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.order-table .size-col .cell,
.order-table .total-col .cell {
  padding: 0 !important;
  height: 100%;
}

.cell-total {
  font-weight: 600;
  color: #303133;
}

.parsed-remark {
  margin-top: 10px;
}

.detail-footer {
  flex-shrink: 0;
  border-top: 1px solid var(--lark-border-light);
  padding: 12px 20px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.footer-form {
  display: flex;
  gap: 12px;
  align-items: center;
}

.footer-actions {
  display: flex;
  gap: 10px;
  align-items: center;
}

@media (max-width: 1400px) {
  .compare-grid {
    grid-template-columns: 420px 1fr;
  }
}

@media (max-width: 1100px) {
  .detail-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }

  .detail-header-right {
    width: 100%;
    flex-wrap: wrap;
  }

  .compare-grid {
    grid-template-columns: 1fr;
  }

  .compare-left {
    border-right: none;
    border-bottom: 1px solid var(--lark-border-light);
    padding-right: 0;
    padding-bottom: 16px;
  }
}
</style>
