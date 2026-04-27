<template>
  <div class="review-page">
    <div class="review-main">
      <!-- ====== 左侧：待审核列表 ====== -->
      <div class="list-panel">
        <div class="list-toolbar">
          <el-select v-model="filters.review_status" clearable placeholder="审核状态" size="default" style="width: 140px" @change="fetchReviews">
            <el-option label="待审核" value="pending" />
            <el-option label="已审核下单" value="approved" />
            <el-option label="已替换旧单" value="replaced" />
            <el-option label="手动录单" value="manual_ordered" />
            <el-option label="废单" value="voided" />
          </el-select>
          <el-button class="lark-btn-secondary" size="default" @click="fetchReviews">刷新</el-button>
          <span class="list-total">{{ pagination.total }} 条</span>
        </div>

        <el-scrollbar class="list-scroll">
          <div
            v-for="item in reviewList"
            :key="item.id"
            class="review-list-item"
            :class="{ active: selectedReview?.id === item.id }"
            @click="selectReview(item)"
          >
            <div class="review-item-head">
              <span class="room-name">{{ item.room_name || '未命名群聊' }}</span>
              <el-tag size="small" :type="statusTagType(item.review_status)">{{ statusText(item.review_status) }}</el-tag>
            </div>
            <div class="review-item-meta">
              <span>{{ item.customer_name || '未匹配客户' }}</span>
              <span>{{ formatDate(item.created_at) }}</span>
            </div>
            <div class="review-item-desc">{{ item.content_text || item.attachment_name || '无文本内容' }}</div>
          </div>
          <el-empty v-if="!reviewLoading && reviewList.length === 0" description="暂无数据" :image-size="64" />
        </el-scrollbar>

        <div class="list-pagination">
          <el-pagination
            v-model:current-page="pagination.page"
            v-model:page-size="pagination.pageSize"
            :total="pagination.total"
            :page-sizes="[10, 20, 50]"
            small
            layout="prev, pager, next"
            @size-change="fetchReviews"
            @current-change="fetchReviews"
          />
        </div>
      </div>

      <!-- ====== 右侧：审核详情 ====== -->
      <div class="detail-panel">
        <template v-if="selectedReview">
          <!-- 顶部信息栏 -->
          <div class="detail-header">
            <div class="detail-header-left">
              <span class="detail-room">{{ selectedReview.room_name || '未命名群聊' }}</span>
              <span v-if="selectedReview.sender_name" class="detail-sender">/ {{ selectedReview.sender_name }}</span>
              <el-tag size="small" :type="statusTagType(selectedReview.review_status)" style="margin-left:8px">{{ statusText(selectedReview.review_status) }}</el-tag>
            </div>
            <el-button class="lark-btn-secondary" size="default" @click="handleReparse" :loading="actionLoading">重新解析</el-button>
          </div>

          <!-- 中间对比区：左原始消息 / 右解析结果 -->
          <div class="detail-body">
            <div class="compare-grid">
              <div class="compare-left">
                <div class="panel-label">原始消息</div>
                <div class="msg-meta-row">
                  <span>类型：{{ selectedReview.message_type || '-' }}</span>
                  <span>附件：{{ selectedReview.attachment_name || '-' }}</span>
                </div>
                <pre class="raw-block">{{ formatRawMessage(selectedReview) }}</pre>
              </div>

              <div class="compare-right">
                <div class="panel-label">解析结果（下单内容）</div>
                <template v-if="currentOrder">
                  <div class="order-info-bar">
                    <span>客户：<strong>{{ currentOrder.customer_name || selectedReview.customer_name || '-' }}</strong></span>
                    <span>联系人：<strong>{{ currentOrder.contact_person || '-' }}</strong></span>
                    <span>下单时间：<strong>{{ currentOrder.order_date || '-' }}</strong></span>
                    <span v-if="currentOrder.remark">备注：<strong>{{ currentOrder.remark }}</strong></span>
                  </div>
                  <el-table :data="currentOrder.items || []" border size="small" class="order-table" max-height="380">
                    <el-table-column type="index" label="#" width="42" align="center" />
                    <el-table-column prop="product_no" label="款号" min-width="120" show-overflow-tooltip />
                    <el-table-column prop="color" label="颜色" min-width="90" show-overflow-tooltip />
                    <el-table-column label="尺码 × 数量" min-width="180">
                      <template #default="{ row }">
                        {{ formatSizes(row.sizes) }}
                      </template>
                    </el-table-column>
                    <el-table-column prop="remark" label="备注" min-width="110" show-overflow-tooltip />
                  </el-table>
                  <div v-if="currentOrder.uncertainties?.length" class="uncertainty-box">
                    <div class="uncertainty-title">待确认信息</div>
                    <div v-for="(u, idx) in currentOrder.uncertainties" :key="idx" class="uncertainty-item">{{ u }}</div>
                  </div>
                </template>
                <el-empty v-else description="暂无解析结果" :image-size="48" />
              </div>
            </div>
          </div>

          <!-- 底部操作栏 -->
          <div class="detail-footer">
            <div class="footer-form">
              <el-select v-model="selectedCustomerId" filterable placeholder="请选择客户" style="width: 260px">
                <el-option v-for="c in customerOptions" :key="c.id" :label="`${c.customer_name}${c.erp_customer_id ? ` (${c.erp_customer_id})` : ''}`" :value="c.id" />
              </el-select>
              <el-input v-model="reviewNote" placeholder="审核备注（选填）" style="flex:1" />
            </div>
            <div class="footer-actions">
              <el-button type="primary" :loading="actionLoading" @click="handleApprove">审核下单</el-button>
              <el-button type="warning" :loading="actionLoading" @click="handleReplace">替换旧单</el-button>
              <el-button type="success" :loading="actionLoading" @click="openManualDialog">手动录单</el-button>
              <el-button type="danger" plain :loading="actionLoading" @click="handleVoid">废单</el-button>
            </div>
          </div>
        </template>
        <el-empty v-else description="请选择左侧消息查看详情" class="detail-empty" />
      </div>
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
  review_status: 'pending'
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
  try {
    const res = await getCustomerList({ page: 1, pageSize: 500 })
    customerOptions.value = res?.data?.list || []
  } catch {
    customerOptions.value = []
  }
}

const fetchReviews = async () => {
  reviewLoading.value = true
  try {
    const res = await getReviewList({
      page: pagination.page,
      pageSize: pagination.pageSize,
      review_status: filters.review_status || undefined
    })
    reviewList.value = res?.data?.list || []
    pagination.total = res?.data?.total || 0
    if (reviewList.value.length > 0) {
      const targetId = selectedReview.value?.id
      const matched = reviewList.value.find(item => item.id === targetId) || reviewList.value[0]
      await selectReview(matched)
    } else {
      selectedReview.value = null
    }
  } catch {
    reviewList.value = []
    pagination.total = 0
    selectedReview.value = null
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
/* ===== 整体布局 ===== */
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

/* ===== 左侧列表面板 ===== */
.list-panel {
  width: 320px;
  flex-shrink: 0;
  background: var(--lark-bg-base);
  border-radius: var(--lark-radius-lg);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.list-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--lark-border-light);
  flex-shrink: 0;
}

.list-total {
  margin-left: auto;
  font-size: 12px;
  color: var(--lark-text-secondary);
  white-space: nowrap;
}

.list-scroll {
  flex: 1;
  min-height: 0;
  padding: 8px 10px;
}

.list-pagination {
  flex-shrink: 0;
  display: flex;
  justify-content: center;
  padding: 8px 0;
  border-top: 1px solid var(--lark-border-light);
}

/* 列表项 */
.review-list-item {
  border: 1px solid var(--lark-border-light);
  border-radius: 10px;
  padding: 10px 12px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.review-list-item:hover {
  background: var(--lark-bg-hover);
}

.review-list-item.active {
  border-color: var(--lark-primary);
  background: var(--lark-primary-light);
}

.review-item-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.room-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--lark-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.review-item-meta {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--lark-text-secondary);
  margin-bottom: 6px;
}

.review-item-desc {
  font-size: 13px;
  color: var(--lark-text-regular);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* ===== 右侧详情面板 ===== */
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

/* 顶栏 */
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

/* 中间内容区 */
.detail-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 16px 20px;
}

.compare-grid {
  display: grid;
  grid-template-columns: 340px 1fr;
  gap: 16px;
  min-height: 100%;
}

.compare-left,
.compare-right {
  display: flex;
  flex-direction: column;
}

.compare-left {
  border-right: 1px solid var(--lark-border-light);
  padding-right: 16px;
}

.panel-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--lark-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 10px;
}

.msg-meta-row {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: var(--lark-text-secondary);
  margin-bottom: 10px;
}

.raw-block {
  flex: 1;
  background: #f7f8fa;
  border-radius: 8px;
  padding: 12px;
  font-size: 12px;
  line-height: 1.6;
  color: #334155;
  white-space: pre-wrap;
  word-break: break-word;
  overflow: auto;
  margin: 0;
}

.order-info-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  font-size: 13px;
  color: var(--lark-text-regular);
  margin-bottom: 12px;
}

.order-table {
  margin-bottom: 8px;
}

.uncertainty-box {
  margin-top: 12px;
  background: #fff7e6;
  border: 1px solid #ffd591;
  border-radius: 8px;
  padding: 10px 12px;
}

.uncertainty-title {
  font-weight: 600;
  font-size: 13px;
  margin-bottom: 6px;
}

.uncertainty-item {
  font-size: 13px;
  color: #8c6d1f;
  margin-bottom: 3px;
}

/* 底部操作栏 */
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

/* 手动录单弹窗 */
.manual-top-row {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 12px;
}

.manual-actions,
.dialog-footer {
  margin-top: 12px;
  display: flex;
  justify-content: space-between;
}

/* 响应式 */
@media (max-width: 1200px) {
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
