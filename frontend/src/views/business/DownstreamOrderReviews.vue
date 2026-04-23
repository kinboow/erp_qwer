<template>
  <div class="review-page">
    <div class="lark-page-header">
      <div class="header-title">订单待审核</div>
      <div class="header-desc">接收企微客户群消息，AI 解析后进入人工审核，再决定下单、替换旧单、手动录单或废单。</div>
    </div>

    <div class="toolbar-card">
      <div class="toolbar-left">
        <el-select v-model="filters.review_status" clearable placeholder="审核状态" style="width: 180px" @change="fetchReviews">
          <el-option label="待审核" value="pending" />
          <el-option label="已审核下单" value="approved" />
          <el-option label="已替换旧单" value="replaced" />
          <el-option label="手动录单" value="manual_ordered" />
          <el-option label="废单" value="voided" />
        </el-select>
        <el-button class="lark-btn-secondary" @click="fetchReviews">刷新</el-button>
      </div>
      <div class="toolbar-right">
        <span class="summary-text">共 {{ pagination.total }} 条待审核消息</span>
      </div>
    </div>

    <div class="review-layout">
      <div class="review-list-card">
        <div class="card-title">消息列表</div>
        <el-scrollbar height="calc(100vh - 270px)">
          <div
            v-for="item in reviewList"
            :key="item.id"
            class="review-list-item"
            :class="{ active: selectedReview?.id === item.id }"
            @click="selectReview(item)"
          >
            <div class="review-item-head">
              <div class="room-name">{{ item.room_name || '未命名群聊' }}</div>
              <el-tag size="small" :type="statusTagType(item.review_status)">{{ statusText(item.review_status) }}</el-tag>
            </div>
            <div class="review-item-meta">
              <span>{{ item.customer_name || '未匹配客户' }}</span>
              <span>{{ formatDate(item.created_at) }}</span>
            </div>
            <div class="review-item-desc">{{ item.content_text || item.attachment_name || '无文本内容' }}</div>
          </div>
          <el-empty v-if="!reviewLoading && reviewList.length === 0" description="暂无待审核消息" />
        </el-scrollbar>
      </div>

      <div class="review-detail-card">
        <div v-if="selectedReview" class="detail-inner">
          <div class="detail-head">
            <div>
              <div class="card-title">审核详情</div>
              <div class="detail-subtitle">
                {{ selectedReview.room_name || '未命名群聊' }}
                <span v-if="selectedReview.sender_name"> / {{ selectedReview.sender_name }}</span>
              </div>
            </div>
            <div class="detail-actions-top">
              <el-button class="lark-btn-secondary" @click="handleReparse" :loading="actionLoading">重新解析</el-button>
            </div>
          </div>

          <div class="compare-grid">
            <div class="compare-panel">
              <div class="panel-title">原始消息</div>
              <div class="message-meta">
                <span>消息类型：{{ selectedReview.message_type || '-' }}</span>
                <span>附件：{{ selectedReview.attachment_name || '-' }}</span>
              </div>
              <pre class="json-block">{{ formatRawMessage(selectedReview) }}</pre>
            </div>

            <div class="compare-panel">
              <div class="panel-title">解析结果</div>
              <template v-if="currentOrder">
                <div class="parsed-summary">
                  <div class="summary-row"><span>客户：</span><strong>{{ currentOrder.customer_name || selectedReview.customer_name || '-' }}</strong></div>
                  <div class="summary-row"><span>联系人：</span><strong>{{ currentOrder.contact_person || '-' }}</strong></div>
                  <div class="summary-row"><span>下单时间：</span><strong>{{ currentOrder.order_date || '-' }}</strong></div>
                  <div class="summary-row"><span>备注：</span><strong>{{ currentOrder.remark || '-' }}</strong></div>
                </div>
                <el-table :data="currentOrder.items || []" border size="small" class="parsed-table">
                  <el-table-column prop="product_no" label="款号" min-width="120" />
                  <el-table-column prop="color" label="颜色" min-width="100" />
                  <el-table-column label="尺码数量" min-width="180">
                    <template #default="{ row }">
                      {{ formatSizes(row.sizes) }}
                    </template>
                  </el-table-column>
                  <el-table-column prop="remark" label="备注" min-width="120" show-overflow-tooltip />
                </el-table>
                <div v-if="currentOrder.uncertainties?.length" class="uncertainty-box">
                  <div class="uncertainty-title">待确认信息</div>
                  <div v-for="(item, index) in currentOrder.uncertainties" :key="index" class="uncertainty-item">{{ item }}</div>
                </div>
              </template>
              <el-empty v-else description="暂无解析结果" />
            </div>
          </div>

          <div class="action-panel">
            <div class="action-form-row">
              <el-select v-model="selectedCustomerId" filterable placeholder="请选择客户" style="width: 280px">
                <el-option v-for="item in customerOptions" :key="item.id" :label="`${item.customer_name}${item.erp_customer_id ? ` (${item.erp_customer_id})` : ''}`" :value="item.id" />
              </el-select>
              <el-input v-model="reviewNote" placeholder="审核备注（选填）" />
            </div>
            <div class="action-buttons">
              <el-button type="primary" :loading="actionLoading" @click="handleApprove">审核</el-button>
              <el-button type="warning" :loading="actionLoading" @click="handleReplace">替换旧单</el-button>
              <el-button type="success" :loading="actionLoading" @click="openManualDialog">手动录单</el-button>
              <el-button type="danger" plain :loading="actionLoading" @click="handleVoid">废单</el-button>
            </div>
          </div>
        </div>
        <el-empty v-else description="请选择左侧消息查看详情" />
      </div>
    </div>

    <div class="pagination-wrap">
      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.pageSize"
        :total="pagination.total"
        :page-sizes="[10, 20, 50]"
        layout="sizes, prev, pager, next, jumper"
        @size-change="fetchReviews"
        @current-change="fetchReviews"
      />
    </div>

    <el-dialog v-model="manualDialogVisible" title="手动录单" width="860px" destroy-on-close>
      <div class="manual-top-row">
        <el-select v-model="manualCustomerId" filterable placeholder="请选择客户" style="width: 260px">
          <el-option v-for="item in customerOptions" :key="item.id" :label="`${item.customer_name}${item.erp_customer_id ? ` (${item.erp_customer_id})` : ''}`" :value="item.id" />
        </el-select>
        <el-input v-model="manualForm.remark" placeholder="订单备注" />
      </div>
      <el-table :data="manualForm.items" border size="small">
        <el-table-column label="款号" min-width="130">
          <template #default="{ row }">
            <el-input v-model="row.product_no" placeholder="款号" />
          </template>
        </el-table-column>
        <el-table-column label="颜色" min-width="100">
          <template #default="{ row }">
            <el-input v-model="row.color" placeholder="颜色" />
          </template>
        </el-table-column>
        <el-table-column label="尺码" min-width="90">
          <template #default="{ row }">
            <el-input v-model="row.size" placeholder="尺码" />
          </template>
        </el-table-column>
        <el-table-column label="数量" min-width="90">
          <template #default="{ row }">
            <el-input-number v-model="row.qty" :min="1" :step="1" style="width: 100%" />
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="140">
          <template #default="{ row }">
            <el-input v-model="row.remark" placeholder="备注" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="90">
          <template #default="{ $index }">
            <el-button link type="danger" @click="removeManualRow($index)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="manual-actions">
        <el-button class="lark-btn-secondary" @click="addManualRow">新增一行</el-button>
      </div>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="manualDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="actionLoading" @click="submitManualOrder">提交手动录单</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getCustomerList } from '@/api/customer'
import {
  approveReview,
  getReviewDetail,
  getReviewList,
  manualReview,
  replaceReview,
  reparseReview,
  voidReview
} from '@/api/downstreamOrders'

const reviewLoading = ref(false)
const actionLoading = ref(false)
const reviewList = ref([])
const selectedReview = ref(null)
const customerOptions = ref([])
const selectedCustomerId = ref(null)
const reviewNote = ref('')
const manualDialogVisible = ref(false)
const manualCustomerId = ref(null)

const filters = reactive({
  review_status: ''
})

const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
})

const manualForm = reactive({
  remark: '',
  items: []
})

const currentOrder = computed(() => {
  if (!selectedReview.value) return null
  return selectedReview.value.manual_order || selectedReview.value.parsed_order || null
})

const createManualRow = () => ({
  product_no: '',
  color: '',
  size: '',
  qty: 1,
  remark: ''
})

const statusText = (status) => {
  const map = {
    pending: '待审核',
    approved: '已审核下单',
    replaced: '已替换旧单',
    manual_ordered: '手动录单',
    voided: '废单'
  }
  return map[status] || status || '-'
}

const statusTagType = (status) => {
  const map = {
    pending: 'info',
    approved: 'success',
    replaced: 'warning',
    manual_ordered: 'success',
    voided: 'danger'
  }
  return map[status] || 'info'
}

const formatDate = (value) => {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN')
}

const formatSizes = (sizes = []) => {
  return (sizes || []).map(item => `${item.size}:${item.qty}`).join('，') || '-'
}

const formatRawMessage = (row) => {
  const payload = row?.callback_payload || {}
  if (Object.keys(payload).length) {
    return JSON.stringify(payload, null, 2)
  }
  return row?.content_text || row?.attachment_name || '无原始内容'
}

const fetchCustomers = async () => {
  const res = await getCustomerList({ page: 1, pageSize: 500 })
  customerOptions.value = res.data.list || []
}

const fetchReviews = async () => {
  reviewLoading.value = true
  try {
    const res = await getReviewList({
      page: pagination.page,
      pageSize: pagination.pageSize,
      review_status: filters.review_status || undefined
    })
    reviewList.value = res.data.list || []
    pagination.total = res.data.total || 0
    if (reviewList.value.length > 0) {
      const targetId = selectedReview.value?.id
      const matched = reviewList.value.find(item => item.id === targetId) || reviewList.value[0]
      await selectReview(matched)
    } else {
      selectedReview.value = null
    }
  } finally {
    reviewLoading.value = false
  }
}

const selectReview = async (item) => {
  const res = await getReviewDetail(item.id)
  selectedReview.value = res.data
  selectedCustomerId.value = res.data.customer_id || null
  reviewNote.value = res.data.review_note || ''
}

const ensureCustomerSelected = () => {
  if (!selectedCustomerId.value) {
    ElMessage.warning('请先选择客户')
    return false
  }
  return true
}

const handleReparse = async () => {
  if (!selectedReview.value) return
  actionLoading.value = true
  try {
    await reparseReview(selectedReview.value.id)
    ElMessage.success('重新解析成功')
    await selectReview(selectedReview.value)
    await fetchReviews()
  } finally {
    actionLoading.value = false
  }
}

const handleApprove = async () => {
  if (!selectedReview.value || !ensureCustomerSelected()) return
  actionLoading.value = true
  try {
    await approveReview(selectedReview.value.id, {
      customer_id: selectedCustomerId.value,
      review_note: reviewNote.value
    })
    ElMessage.success('审核下单成功')
    await fetchReviews()
  } finally {
    actionLoading.value = false
  }
}

const handleReplace = async () => {
  if (!selectedReview.value || !ensureCustomerSelected()) return
  await ElMessageBox.confirm('确认先取消该客户未发货旧单，再下新的销售单吗？', '替换旧单', {
    confirmButtonText: '确认',
    cancelButtonText: '取消',
    type: 'warning'
  })
  actionLoading.value = true
  try {
    await replaceReview(selectedReview.value.id, {
      customer_id: selectedCustomerId.value,
      review_note: reviewNote.value
    })
    ElMessage.success('替换旧单成功')
    await fetchReviews()
  } finally {
    actionLoading.value = false
  }
}

const handleVoid = async () => {
  if (!selectedReview.value) return
  await ElMessageBox.confirm('确认将该消息标记为废单吗？', '废单确认', {
    confirmButtonText: '确认',
    cancelButtonText: '取消',
    type: 'warning'
  })
  actionLoading.value = true
  try {
    await voidReview(selectedReview.value.id, { review_note: reviewNote.value })
    ElMessage.success('已标记为废单')
    await fetchReviews()
  } finally {
    actionLoading.value = false
  }
}

const addManualRow = () => {
  manualForm.items.push(createManualRow())
}

const removeManualRow = (index) => {
  manualForm.items.splice(index, 1)
  if (manualForm.items.length === 0) addManualRow()
}

const openManualDialog = () => {
  if (!selectedReview.value) return
  manualCustomerId.value = selectedCustomerId.value || selectedReview.value.customer_id || null
  manualForm.remark = currentOrder.value?.remark || reviewNote.value || ''
  manualForm.items = (currentOrder.value?.items || []).map(item => ({
    product_no: item.product_no || '',
    color: item.color || '',
    size: item.sizes?.[0]?.size || '',
    qty: item.sizes?.[0]?.qty || 1,
    remark: item.remark || ''
  }))
  if (manualForm.items.length === 0) addManualRow()
  manualDialogVisible.value = true
}

const submitManualOrder = async () => {
  if (!selectedReview.value) return
  if (!manualCustomerId.value) {
    ElMessage.warning('请选择客户')
    return
  }
  const items = manualForm.items
    .filter(item => item.product_no && item.size && item.qty)
    .map(item => ({
      product_no: item.product_no,
      color: item.color,
      remark: item.remark,
      sizes: [{ size: item.size, qty: item.qty }]
    }))
  if (items.length === 0) {
    ElMessage.warning('请至少填写一条完整的手动录单明细')
    return
  }

  actionLoading.value = true
  try {
    await manualReview(selectedReview.value.id, {
      customer_id: manualCustomerId.value,
      review_note: reviewNote.value,
      order_data: {
        customer_name: customerOptions.value.find(item => item.id === manualCustomerId.value)?.customer_name || '',
        order_date: new Date().toISOString().slice(0, 19).replace('T', ' '),
        remark: manualForm.remark,
        items
      }
    })
    manualDialogVisible.value = false
    ElMessage.success('手动录单成功')
    await fetchReviews()
  } finally {
    actionLoading.value = false
  }
}

onMounted(async () => {
  await fetchCustomers()
  await fetchReviews()
})
</script>

<style scoped>
.review-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.lark-page-header {
  margin-bottom: 4px;
}

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

.toolbar-card,
.review-list-card,
.review-detail-card {
  background: var(--lark-bg-base);
  border-radius: var(--lark-radius-lg);
  padding: 16px 20px;
}

.toolbar-card {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.toolbar-left,
.toolbar-right,
.action-form-row,
.action-buttons,
.manual-top-row {
  display: flex;
  gap: 12px;
  align-items: center;
}

.summary-text,
.detail-subtitle,
.message-meta {
  color: var(--lark-text-secondary);
  font-size: 13px;
}

.review-layout {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 16px;
}

.card-title,
.panel-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--lark-text-primary);
}

.review-list-item {
  border: 1px solid var(--lark-border-light);
  border-radius: 12px;
  padding: 12px;
  margin-bottom: 10px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.review-list-item:hover,
.review-list-item.active {
  border-color: var(--lark-primary);
  background: var(--lark-primary-light);
}

.review-item-head,
.review-item-meta,
.detail-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.review-item-head {
  margin-bottom: 8px;
}

.review-item-meta {
  font-size: 12px;
  color: var(--lark-text-secondary);
  margin-bottom: 8px;
}

.review-item-desc {
  font-size: 13px;
  color: var(--lark-text-regular);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.detail-inner {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.compare-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.compare-panel {
  border: 1px solid var(--lark-border-light);
  border-radius: 12px;
  padding: 14px;
  min-height: 420px;
}

.message-meta,
.parsed-summary {
  margin-top: 10px;
  margin-bottom: 12px;
}

.message-meta {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.summary-row {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 13px;
}

.json-block {
  background: #f7f8fa;
  border-radius: 8px;
  padding: 12px;
  font-size: 12px;
  line-height: 1.6;
  color: #334155;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 500px;
  overflow: auto;
}

.parsed-table {
  margin-top: 8px;
}

.uncertainty-box {
  margin-top: 14px;
  background: #fff7e6;
  border: 1px solid #ffd591;
  border-radius: 8px;
  padding: 12px;
}

.uncertainty-title {
  font-weight: 600;
  margin-bottom: 8px;
}

.uncertainty-item {
  font-size: 13px;
  color: #8c6d1f;
  margin-bottom: 4px;
}

.action-panel {
  border-top: 1px solid var(--lark-border-light);
  padding-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.action-form-row {
  display: grid;
  grid-template-columns: 280px 1fr;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
}

.manual-actions,
.dialog-footer {
  margin-top: 12px;
  display: flex;
  justify-content: space-between;
}

@media (max-width: 1200px) {
  .review-layout,
  .compare-grid,
  .action-form-row {
    grid-template-columns: 1fr;
  }
}
</style>
