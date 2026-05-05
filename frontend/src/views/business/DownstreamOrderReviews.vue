<template>
  <div class="review-page">
    <div class="review-main">
      <!-- ====== 审核详情（全宽） ====== -->
      <div class="detail-panel">
        <template v-if="selectedReview">
          <!-- 顶部信息栏 -->
          <div class="detail-header">
            <div class="detail-header-left">
              <el-button :disabled="!hasPrev" @click="goPrev" size="default">&laquo; 上一条</el-button>
              <span class="nav-index">{{ currentIndex + 1 }} / {{ pagination.total }}</span>
              <el-button :disabled="!hasNext" @click="goNext" size="default">下一条 &raquo;</el-button>
              <el-divider direction="vertical" />
              <span class="detail-room">{{ selectedReview.room_name || '未命名群聊' }}</span>
              <span v-if="selectedReview.sender_name" class="detail-sender">/ {{ selectedReview.sender_name }}</span>
              <el-tag size="small" :type="statusTagType(selectedReview.review_status)" style="margin-left:8px">{{ statusText(selectedReview.review_status) }}</el-tag>
              <span v-if="selectedReview.review_uid" class="detail-uid">{{ selectedReview.review_uid }}</span>
            </div>
            <div class="detail-header-right">
              <el-select v-model="filters.review_status" size="default" style="width: 130px" @change="fetchReviews">
                <el-option label="待审核" value="pending" />
                <el-option label="已审核下单" value="approved" />
                <el-option label="已替换旧单" value="replaced" />
                <el-option label="手动录单" value="manual_ordered" />
                <el-option label="废单" value="voided" />
                <el-option label="异常" value="exception" />
              </el-select>
            </div>
          </div>

          <!-- 中间对比区：左原始消息 / 右解析结果 -->
          <div class="detail-body">
            <div class="compare-grid">
              <div class="compare-left">
                <el-tabs v-model="leftTab" class="left-tabs">
                  <el-tab-pane label="群聊上下文" name="chat">
                    <div class="chat-panel" ref="chatContainerRef">
                      <div v-if="contextLoading" class="chat-loading">
                        <el-icon class="is-loading"><Loading /></el-icon> 加载聊天记录...
                      </div>
                      <template v-else-if="contextMessages.length > 0">
                        <template v-for="(msg, idx) in contextMessages" :key="msg.id">
                          <div v-if="shouldShowTime(idx)" class="chat-time-sep">{{ formatChatTime(msg.created_at) }}</div>
                          <div
                            class="chat-msg"
                            :class="{
                              'is-trigger': msg.id === triggerMsgId,
                              'is-review': reviewMsgIds.includes(msg.id) && msg.id !== triggerMsgId,
                              'is-bot': isBotMsg(msg),
                            }"
                          >
                            <div class="chat-sender-line" v-if="!isBotMsg(msg)">
                              {{ msg.sender_name || msg.sender_id || '未知' }}<span class="chat-sender-via">@ 微信</span>
                              <el-tag v-if="msg.id === triggerMsgId" size="small" type="primary" class="chat-tag">本单触发</el-tag>
                              <el-tag v-else-if="reviewMsgIds.includes(msg.id)" size="small" type="info" class="chat-tag">关联审核单</el-tag>
                            </div>
                            <div class="chat-bubble" :class="{ 'bubble-bot': isBotMsg(msg), 'bubble-trigger': msg.id === triggerMsgId }">
                              <template v-if="msg.message_type === 'image'">
                                <img
                                  v-if="msg.media_url"
                                  :src="mediaUrl(msg.media_url)"
                                  class="chat-inline-image"
                                  loading="lazy"
                                  @click="previewImage(mediaUrl(msg.media_url))"
                                />
                                <img
                                  v-else-if="msg.image_base64"
                                  :src="`data:${msg.image_mime || 'image/png'};base64,${msg.image_base64}`"
                                  class="chat-inline-image"
                                  @click="previewImage(`data:${msg.image_mime || 'image/png'};base64,${msg.image_base64}`)"
                                />
                                <div v-else class="chat-img-placeholder">
                                  <el-icon class="placeholder-icon"><WarningFilled /></el-icon>
                                  <span>图片失效</span>
                                </div>
                              </template>
                              <template v-else-if="msg.message_type === 'file'">
                                <div class="chat-file-wrap">
                                  <el-icon><Document /></el-icon>
                                  <a v-if="msg.media_url" :href="mediaUrl(msg.media_url)" target="_blank" class="chat-file-link">{{ msg.content_preview || '[文件]' }}</a>
                                  <span v-else>{{ msg.content_preview || '[文件]' }}</span>
                                </div>
                              </template>
                              <template v-else>
                                <span class="chat-text">{{ msg.content_preview || '[空消息]' }}</span>
                              </template>
                            </div>
                          </div>
                        </template>
                      </template>
                      <el-empty v-else description="暂无聊天记录" :image-size="48" />
                    </div>
                  </el-tab-pane>
                  <el-tab-pane label="信息来源" name="source">
                    <div class="source-panel">
                      <template v-if="triggerMsg">
                        <div
                          v-if="triggerMsg.message_type === 'image' && (triggerMsg.media_url || triggerMsg.image_base64)"
                          class="source-img-viewport"
                          ref="sourceViewportRef"
                          @wheel.prevent="onSourceWheel"
                          @mousedown="onSourceMouseDown"
                        >
                          <img
                            :src="triggerMsg.media_url ? mediaUrl(triggerMsg.media_url) : `data:${triggerMsg.image_mime || 'image/png'};base64,${triggerMsg.image_base64}`"
                            class="source-preview-img"
                            :style="sourceImgStyle"
                            draggable="false"
                          />
                        </div>
                        <div v-else-if="triggerMsg.message_type === 'file'" class="source-file-info">
                          <el-icon><Document /></el-icon>
                          <a v-if="triggerMsg.media_url" :href="mediaUrl(triggerMsg.media_url)" target="_blank" class="chat-file-link">{{ triggerMsg.content_preview || '[文件]' }}</a>
                          <span v-else>{{ triggerMsg.content_preview || '[文件]' }}</span>
                        </div>
                        <div v-else class="source-text">{{ triggerMsg.content_preview || '[无内容]' }}</div>
                      </template>
                      <el-empty v-else description="暂无来源信息" :image-size="48" />
                    </div>
                  </el-tab-pane>
                  <el-tab-pane name="uncertain" v-if="hasUncertainties">
                    <template #label>
                      <span class="tab-label-badge">待确认<span class="red-dot"></span></span>
                    </template>
                    <div class="uncertain-panel">
                      <div v-for="(u, idx) in currentOrder.uncertainties" :key="idx" class="uncertain-item">{{ u }}</div>
                    </div>
                  </el-tab-pane>
                </el-tabs>
              </div>

              <!-- 图片预览（支持缩放/旋转） -->
              <el-image-viewer
                v-if="previewImageUrl"
                :url-list="[previewImageUrl]"
                :initial-index="0"
                @close="previewImageUrl = ''"
                teleported
              />

              <div class="compare-right">
                <div class="panel-label">解析结果（下单内容）</div>
                <div class="edit-form-area">
                  <el-table :data="editForm.items" border size="small" class="order-table" @keydown="onTableKeydown">
                    <el-table-column type="index" label="序" width="40" align="center" />
                    <el-table-column label="款号" min-width="90" align="center" header-align="center" class-name="select-col">
                      <template #default="{ row }">
                        <select class="cell-native-select" :value="row.product_no" @change="row.product_no = $event.target.value; row.color = ''">
                          <option value="">款号</option>
                          <option v-for="pno in productNos" :key="pno" :value="pno">{{ pno }}</option>
                        </select>
                      </template>
                    </el-table-column>
                    <el-table-column label="颜色" min-width="80" align="center" header-align="center" class-name="select-col">
                      <template #default="{ row }">
                        <select class="cell-native-select" :value="row.color" @change="row.color = $event.target.value">
                          <option value="">颜色</option>
                          <option v-for="c in (colorsByPno[row.product_no] || [])" :key="c" :value="c">{{ c }}</option>
                        </select>
                      </template>
                    </el-table-column>
                    <el-table-column v-for="s in STANDARD_SIZES" :key="s" :label="s" width="58" align="center" class-name="size-col">
                      <template #default="{ row }">
                        <input
                          type="number"
                          class="cell-input"
                          :class="{ 'cell-disabled': isSizeDisabled(row, s) }"
                          :value="row[`s_${s}`] || ''"
                          :disabled="isSizeDisabled(row, s)"
                          @input="row[`s_${s}`] = parseInt($event.target.value) || 0"
                          @focus="$event.target.select()"
                          min="0"
                        />
                      </template>
                    </el-table-column>
                    <el-table-column label="合计" width="54" align="center" class-name="total-col">
                      <template #default="{ row }">
                        <span class="cell-total">{{ rowTotal(row) }}</span>
                      </template>
                    </el-table-column>
                    <el-table-column label="操作" width="52" align="center">
                      <template #default="{ $index }">
                        <el-button link type="danger" size="small" @click="removeEditRow($index)">删除</el-button>
                      </template>
                    </el-table-column>
                  </el-table>
                  <div class="edit-form-actions">
                    <el-button class="lark-btn-secondary" size="small" @click="addEditRow">新增一行</el-button>
                    <el-button type="primary" size="small" @click="saveEditForm">保存修改</el-button>
                    <el-button type="danger" size="small" @click="populateEditForm">还原解析</el-button>
                  </div>
                </div>
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
              <template v-if="selectedReview.review_status === 'pending'">
                <el-button type="primary" :loading="actionLoading" @click="handleApprove">审核下单</el-button>
                <el-button type="warning" :loading="actionLoading" @click="handleReplace">替换旧单</el-button>
                <el-button type="danger" plain :loading="actionLoading" @click="handleVoid">废单</el-button>
              </template>
              <template v-else-if="selectedReview.review_status === 'voided' || selectedReview.review_status === 'exception'">
                <el-button type="primary" :loading="actionLoading" @click="handleRevertPending">转为待审核</el-button>
              </template>
            </div>
          </div>
        </template>
        <el-empty v-else :description="reviewLoading ? '加载中...' : '暂无待审核数据'" class="detail-empty" />
      </div>
    </div>

    <el-dialog v-model="manualDialogVisible" title="手动改单" width="92vw" top="5vh" destroy-on-close>
      <div class="manual-split">
        <!-- 左：信息来源 -->
        <div class="manual-preview">
          <div class="manual-preview-label">信息来源</div>
          <div class="manual-preview-body">
            <template v-if="triggerMsg">
              <img
                v-if="triggerMsg.message_type === 'image' && (triggerMsg.media_url || triggerMsg.image_base64)"
                :src="triggerMsg.media_url ? mediaUrl(triggerMsg.media_url) : `data:${triggerMsg.image_mime || 'image/png'};base64,${triggerMsg.image_base64}`"
                class="manual-preview-img"
                @click="previewImage(triggerMsg.media_url ? mediaUrl(triggerMsg.media_url) : `data:${triggerMsg.image_mime || 'image/png'};base64,${triggerMsg.image_base64}`)"
              />
              <div v-else class="manual-preview-text">{{ triggerMsg.content_preview || '[无内容]' }}</div>
            </template>
            <div v-else class="manual-preview-text" style="color:#999">暂无来源信息</div>
          </div>
        </div>
        <!-- 右：修改表单 -->
        <div class="manual-form">
          <div class="manual-top-row">
            <el-select v-model="manualCustomerId" filterable placeholder="请选择客户" style="width: 220px" size="small">
              <el-option v-for="item in customerOptions" :key="item.id" :label="`${item.customer_name}${item.erp_customer_id ? ` (${item.erp_customer_id})` : ''}`" :value="item.id" />
            </el-select>
            <el-input v-model="manualForm.remark" placeholder="订单备注" size="small" />
          </div>
          <el-table :data="manualForm.items" border size="small" class="manual-table" @keydown="onTableKeydown">
            <el-table-column type="index" label="序" width="40" align="center" />
            <el-table-column label="款号" width="130">
              <template #default="{ row }">
                <el-select v-model="row.product_no" filterable allow-create default-first-option placeholder="款号" size="small" class="cell-select" @change="row.color = ''">
                  <el-option v-for="pno in productNos" :key="pno" :label="pno" :value="pno" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="颜色" width="110">
              <template #default="{ row }">
                <el-select v-model="row.color" filterable allow-create default-first-option placeholder="颜色" size="small" class="cell-select">
                  <el-option v-for="c in (colorsByPno[row.product_no] || [])" :key="c" :label="c" :value="c" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column v-for="s in STANDARD_SIZES" :key="s" :label="s" width="50" align="center">
              <template #default="{ row }">
                <el-input-number v-model="row[`s_${s}`]" :min="0" :step="1" :controls="false" size="small" class="cell-number" :class="{ 'cell-disabled': isSizeDisabled(row, s) }" :disabled="isSizeDisabled(row, s)" />
              </template>
            </el-table-column>
            <el-table-column label="合计" width="50" align="center">
              <template #default="{ row }">
                {{ rowTotal(row) }}
              </template>
            </el-table-column>
            <el-table-column label="" width="52" align="center">
              <template #default="{ $index }">
                <el-button link type="danger" size="small" @click="removeManualRow($index)">删</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div class="manual-actions">
            <el-button class="lark-btn-secondary" size="small" @click="addManualRow">新增一行</el-button>
          </div>
        </div>
      </div>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="manualDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="submitManualOrder">提交修改</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onActivated, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox, ElImageViewer } from 'element-plus'
import { Loading, Picture, Document, WarningFilled } from '@element-plus/icons-vue'
import { getCustomerList } from '@/api/customer'
import { getProductOptions } from '@/api/products'
import {
  approveReview,
  checkDuplicate,
  getContextMessages,
  getReviewDetail,
  getReviewList,
  replaceReview,
  reparseReview,
  revertPending,
  voidReview
} from '@/api/downstreamOrders'

const route = useRoute()
const reviewLoading = ref(false)
const actionLoading = ref(false)
const reviewList = ref([])
const selectedReview = ref(null)
const customerOptions = ref([])
const selectedCustomerId = ref(null)
const reviewNote = ref('')
const manualDialogVisible = ref(false)
const manualCustomerId = ref(null)
const productOptionsRaw = ref([])
const productNos = computed(() => productOptionsRaw.value.map(p => p.product_no))
const colorsByPno = computed(() => {
  const map = {}
  productOptionsRaw.value.forEach(p => { map[p.product_no] = p.colors || [] })
  return map
})
const sizesByPno = computed(() => {
  const map = {}
  productOptionsRaw.value.forEach(p => { map[p.product_no] = p.sizes || [] })
  return map
})
const isSizeDisabled = (row, size) => {
  if (!row.product_no) return true
  const available = sizesByPno.value[row.product_no]
  if (!available || available.length === 0) return true
  return !available.includes(size)
}

const filters = reactive({
  review_status: 'pending'
})

const pagination = reactive({
  page: 1,
  pageSize: 50,
  total: 0
})
const noMoreReviews = ref(false)

const currentIndex = computed(() => {
  if (!selectedReview.value) return -1
  return reviewList.value.findIndex(r => r.id === selectedReview.value.id)
})
const hasPrev = computed(() => currentIndex.value > 0)
const hasNext = computed(() => {
  if (currentIndex.value < 0) return false
  return currentIndex.value < reviewList.value.length - 1 || !noMoreReviews.value
})

const goPrev = async () => {
  if (!hasPrev.value) return
  await selectReview(reviewList.value[currentIndex.value - 1])
}

const goNext = async () => {
  if (!hasNext.value) return
  const nextIdx = currentIndex.value + 1
  if (nextIdx >= reviewList.value.length && !noMoreReviews.value) {
    await loadMoreReviews()
  }
  if (nextIdx < reviewList.value.length) {
    await selectReview(reviewList.value[nextIdx])
  } else if (nextIdx >= reviewList.value.length - 2 && !noMoreReviews.value) {
    await loadMoreReviews()
  }
}

const contextLoading = ref(false)
const contextMessages = ref([])
const triggerMsgId = ref(null)
const reviewMsgIds = ref([])
const chatContainerRef = ref(null)
const previewImageUrl = ref('')
const leftTab = ref('chat')
const sourceViewportRef = ref(null)

const sourceZoom = ref(1)
const sourcePanX = ref(0)
const sourcePanY = ref(0)
let _dragging = false
let _dragStartX = 0
let _dragStartY = 0
let _panStartX = 0
let _panStartY = 0

const sourceImgStyle = computed(() => ({
  transform: `translate(${sourcePanX.value}px, ${sourcePanY.value}px) scale(${sourceZoom.value})`,
  transformOrigin: 'center center',
  cursor: sourceZoom.value > 1 ? (_dragging ? 'grabbing' : 'grab') : 'default'
}))

const resetSourceZoom = () => {
  sourceZoom.value = 1
  sourcePanX.value = 0
  sourcePanY.value = 0
}

const onSourceWheel = (e) => {
  const delta = e.deltaY > 0 ? -0.1 : 0.1
  const next = Math.max(0.2, Math.min(10, sourceZoom.value + delta))
  sourceZoom.value = next
  if (next <= 1) {
    sourcePanX.value = 0
    sourcePanY.value = 0
  }
}

const onSourceMouseDown = (e) => {
  if (sourceZoom.value <= 1) return
  _dragging = true
  _dragStartX = e.clientX
  _dragStartY = e.clientY
  _panStartX = sourcePanX.value
  _panStartY = sourcePanY.value
  const onMove = (ev) => {
    if (!_dragging) return
    sourcePanX.value = _panStartX + (ev.clientX - _dragStartX)
    sourcePanY.value = _panStartY + (ev.clientY - _dragStartY)
  }
  const onUp = () => {
    _dragging = false
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

const manualForm = reactive({
  remark: '',
  items: []
})

const isReviewImage = computed(() => {
  if (!selectedReview.value) return false
  const mt = (selectedReview.value.message_type || '').toLowerCase()
  const mime = (selectedReview.value.attachment_mime || '').toLowerCase()
  return mt === 'image' || mime.startsWith('image/')
})

const STANDARD_SIZES = ['S', 'M', 'L', 'XL', '2XL', '3XL', '4XL', '5XL']

const currentOrder = computed(() => {
  if (!selectedReview.value) return null
  return selectedReview.value.manual_order || selectedReview.value.parsed_order || null
})

const hasUncertainties = computed(() => {
  return currentOrder.value?.uncertainties?.length > 0
})

const triggerMsg = computed(() => {
  if (!triggerMsgId.value) return null
  return contextMessages.value.find(m => m.id === triggerMsgId.value) || null
})

const rowTotal = (row) => {
  return STANDARD_SIZES.reduce((sum, s) => sum + (row[`s_${s}`] || 0), 0)
}

const createManualRow = () => {
  const row = { product_no: '', color: '' }
  STANDARD_SIZES.forEach(s => { row[`s_${s}`] = 0 })
  return row
}

const editForm = reactive({ items: [] })

const populateEditForm = () => {
  const order = currentOrder.value
  editForm.items = (order?.items || []).map(item => {
    const row = { product_no: item.product_no || '', color: item.color || '' }
    STANDARD_SIZES.forEach(s => { row[`s_${s}`] = 0 })
    ;(item.sizes || []).forEach(sz => {
      const key = `s_${sz.size}`
      if (key in row) row[key] = sz.qty || 0
    })
    return row
  })
  if (editForm.items.length === 0) editForm.items.push(createManualRow())
}

const addEditRow = () => {
  editForm.items.push(createManualRow())
}

const removeEditRow = (index) => {
  editForm.items.splice(index, 1)
  if (editForm.items.length === 0) editForm.items.push(createManualRow())
}

const saveEditForm = () => {
  if (!selectedReview.value) return
  const items = editForm.items
    .filter(row => row.product_no && rowTotal(row) > 0)
    .map(row => {
      const sizes = STANDARD_SIZES
        .filter(s => row[`s_${s}`] > 0)
        .map(s => ({ size: s, qty: row[`s_${s}`] }))
      return { product_no: row.product_no, color: row.color, sizes }
    })
  if (items.length === 0) {
    ElMessage.warning('请至少填写一条有数量的明细')
    return
  }
  const orderData = {
    customer_name: customerOptions.value.find(c => c.id === selectedCustomerId.value)?.customer_name || '',
    order_date: new Date().toISOString().slice(0, 19).replace('T', ' '),
    remark: reviewNote.value,
    items
  }
  selectedReview.value.manual_order = orderData
  ElMessage.success('修改已保存')
}

const statusText = (status) => {
  const map = {
    pending: '待审核',
    approved: '已审核下单',
    replaced: '已替换旧单',
    manual_ordered: '手动录单',
    voided: '废单',
    exception: '异常'
  }
  return map[status] || status || '-'
}

const statusTagType = (status) => {
  const map = {
    pending: 'info',
    approved: 'success',
    replaced: 'warning',
    manual_ordered: 'success',
    voided: 'danger',
    exception: 'danger'
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
    const res = await getCustomerList({ page: 1, pageSize: 9999 }, { silentError: true })
    customerOptions.value = res?.data?.list || []
  } catch {
    customerOptions.value = []
  }
}

let _eventSource = null

const _connectSSE = () => {
  _disconnectSSE()
  _eventSource = new EventSource('/api/downstream-orders/reviews/stream')
  _eventSource.onmessage = async (e) => {
    try {
      const payload = JSON.parse(e.data)
      if (payload.event === 'new_review') {
        await _silentRefresh()
        // 新审核单可能来自新客户，静默刷新客户列表
        fetchCustomers()
      }
    } catch {}
  }
  _eventSource.onerror = () => {
    _disconnectSSE()
    setTimeout(_connectSSE, 5000)
  }
}

const _silentRefresh = async () => {
  // 静默刷新列表，保持当前选中项不变
  try {
    const res = await getReviewList({
      page: 1,
      pageSize: Math.max(pagination.pageSize, reviewList.value.length + 10),
      review_status: filters.review_status || undefined,
      sort: 'asc'
    }, { silentError: true })
    const list = res?.data?.list || []
    const newTotal = res?.data?.total || 0
    const currentId = selectedReview.value?.id
    reviewList.value = list
    pagination.total = newTotal
    noMoreReviews.value = list.length >= newTotal
    // 保持当前选中项
    if (currentId) {
      const still = list.find(item => item.id === currentId)
      if (still) {
        selectedReview.value = still
      }
    }
  } catch {}
}

const _disconnectSSE = () => {
  if (_eventSource) { _eventSource.close(); _eventSource = null }
}

const fetchReviews = async (append = false) => {
  if (reviewLoading.value) return
  reviewLoading.value = true
  try {
    if (!append) {
      pagination.page = 1
      noMoreReviews.value = false
    }
    const res = await getReviewList({
      page: pagination.page,
      pageSize: pagination.pageSize,
      review_status: filters.review_status || undefined,
      sort: 'asc'
    }, { silentError: true })
    const list = res?.data?.list || []
    pagination.total = res?.data?.total || 0
    if (append) {
      reviewList.value = [...reviewList.value, ...list]
    } else {
      reviewList.value = list
    }
    if (reviewList.value.length >= pagination.total) {
      noMoreReviews.value = true
    }
    if (!append) {
      if (reviewList.value.length > 0) {
        const queryId = route.query.id ? Number(route.query.id) : null
        const targetId = queryId || selectedReview.value?.id
        const matched = reviewList.value.find(item => item.id === targetId) || reviewList.value[0]
        await selectReview(matched)
      } else {
        selectedReview.value = null
      }
    }
  } catch {
    if (!append) {
      reviewList.value = []
      pagination.total = 0
      selectedReview.value = null
    }
  } finally {
    reviewLoading.value = false
  }
}

const loadMoreReviews = async () => {
  if (noMoreReviews.value || reviewLoading.value) return
  pagination.page++
  await fetchReviews(true)
}

const selectReview = async (item) => {
  resetSourceZoom()
  const res = await getReviewDetail(item.id)
  selectedReview.value = res.data
  selectedCustomerId.value = res.data.customer_id ? Number(res.data.customer_id) : null
  reviewNote.value = res.data.review_note || ''
  populateEditForm()
  await fetchContextMessages(item.id)
}

const fetchContextMessages = async (reviewId) => {
  contextLoading.value = true
  contextMessages.value = []
  triggerMsgId.value = null
  reviewMsgIds.value = []
  try {
    const res = await getContextMessages(reviewId, { silentError: true })
    contextMessages.value = res?.data?.messages || []
    triggerMsgId.value = res?.data?.trigger_msg_id || null
    reviewMsgIds.value = res?.data?.review_msg_ids || []
  } catch {
    contextMessages.value = []
  } finally {
    contextLoading.value = false
    await nextTick()
    scrollToTrigger()
  }
}

const scrollToTrigger = () => {
  const container = chatContainerRef.value
  if (!container) return
  const triggerEl = container.querySelector?.('.is-trigger') || container.$el?.querySelector?.('.is-trigger')
  if (triggerEl) {
    triggerEl.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
}

const previewImage = (src) => {
  previewImageUrl.value = src
}

const isBotMsg = (msg) => {
  const name = (msg.sender_name || '').toLowerCase()
  return name.includes('bot') || name.includes('机器人') || name.includes('助手')
    || (msg.content_preview || '').startsWith('@') && (msg.content_preview || '').includes('订单已识别')
}

const shouldShowTime = (idx) => {
  if (idx === 0) return true
  const cur = contextMessages.value[idx]
  const prev = contextMessages.value[idx - 1]
  if (!cur?.created_at || !prev?.created_at) return false
  const diff = new Date(cur.created_at) - new Date(prev.created_at)
  return diff > 5 * 60 * 1000 // 超过5分钟显示时间
}

const mediaUrl = (url) => {
  if (!url) return ''
  const t = localStorage.getItem('token') || ''
  return `${url}${url.includes('?') ? '&' : '?'}token=${encodeURIComponent(t)}`
}

const formatChatTime = (value) => {
  if (!value) return ''
  const d = new Date(value)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
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

const _printDebugLogs = (d) => {
  if (d?._debug_logs?.length) {
    console.group('%c[ERP 流程耗时]', 'color: #409EFF; font-weight: bold')
    d._debug_logs.forEach(log => console.log(log))
    console.groupEnd()
  }
}

const confirmDuplicates = async (duplicates) => {
  const lines = duplicates.map(d => `订单号: ${d.order_no}，日期: ${d.order_date}，共 ${d.item_count} 行明细`)
  await ElMessageBox.confirm(
    `检测到该客户已有整单完全相同的销售订单：\n\n${lines.join('\n')}\n\n（款号、颜色、尺码、数量全部一致）\n确认仍要继续下单吗？`,
    '重复订单提醒',
    { confirmButtonText: '继续下单', cancelButtonText: '取消', type: 'warning' }
  )
}

const handleApprove = async () => {
  if (!selectedReview.value || !ensureCustomerSelected()) return
  actionLoading.value = true
  try {
    const dupRes = await checkDuplicate(selectedReview.value.id, {
      customer_id: selectedCustomerId.value
    })
    const dups = dupRes.data?.duplicates || []
    if (dups.length > 0) {
      await confirmDuplicates(dups)
    }
    const res = await approveReview(selectedReview.value.id, {
      customer_id: selectedCustomerId.value,
      review_note: reviewNote.value
    })
    const d = res.data || {}
    _printDebugLogs(d)
    let msg = `审核下单成功，ERP单号: ${d.order_no || '-'}，${d.message || ''}`
    if (d.auto_print?.printed) {
      msg += `，${d.auto_print.message || '配货单已加入打印队列'}`
      ElMessage.success(msg)
    } else if (d.auto_print && !d.auto_print.printed) {
      msg += `，自动打印失败: ${d.auto_print.error || '未知错误'}`
      ElMessage({ message: msg, type: 'warning', duration: 6000 })
    } else {
      ElMessage.success(msg)
    }
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
    const dupRes = await checkDuplicate(selectedReview.value.id, {
      customer_id: selectedCustomerId.value
    })
    const dups = dupRes.data?.duplicates || []
    if (dups.length > 0) {
      await confirmDuplicates(dups)
    }
    const res = await replaceReview(selectedReview.value.id, {
      customer_id: selectedCustomerId.value,
      review_note: reviewNote.value
    })
    const d = res.data || {}
    _printDebugLogs(d)
    const replacedInfo = d.replaced_orders?.length ? `，已取消旧单: ${d.replaced_orders.join(', ')}` : ''
    let rMsg = `替换旧单成功，新ERP单号: ${d.order_no || '-'}${replacedInfo}`
    if (d.auto_print?.printed) {
      rMsg += `，${d.auto_print.message || '配货单已加入打印队列'}`
      ElMessage.success(rMsg)
    } else if (d.auto_print && !d.auto_print.printed) {
      rMsg += `，自动打印失败: ${d.auto_print.error || '未知错误'}`
      ElMessage({ message: rMsg, type: 'warning', duration: 6000 })
    } else {
      ElMessage.success(rMsg)
    }
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

const handleRevertPending = async () => {
  if (!selectedReview.value) return
  const label = selectedReview.value.review_status === 'exception' ? '异常单' : '废单'
  await ElMessageBox.confirm(`确认将该${label}转为待审核状态吗？`, '转为待审核', {
    confirmButtonText: '确认',
    cancelButtonText: '取消',
    type: 'info'
  })
  actionLoading.value = true
  try {
    await revertPending(selectedReview.value.id)
    ElMessage.success('已转为待审核')
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
  manualForm.items = (currentOrder.value?.items || []).map(item => {
    const row = { product_no: item.product_no || '', color: item.color || '' }
    STANDARD_SIZES.forEach(s => { row[`s_${s}`] = 0 })
    ;(item.sizes || []).forEach(sz => {
      const key = `s_${sz.size}`
      if (key in row) row[key] = sz.qty || 0
    })
    return row
  })
  if (manualForm.items.length === 0) addManualRow()
  manualDialogVisible.value = true
}

const submitManualOrder = () => {
  if (!selectedReview.value) return
  if (!manualCustomerId.value) {
    ElMessage.warning('请选择客户')
    return
  }
  const items = manualForm.items
    .filter(row => row.product_no && rowTotal(row) > 0)
    .map(row => {
      const sizes = STANDARD_SIZES
        .filter(s => row[`s_${s}`] > 0)
        .map(s => ({ size: s, qty: row[`s_${s}`] }))
      return { product_no: row.product_no, color: row.color, sizes }
    })
  if (items.length === 0) {
    ElMessage.warning('请至少填写一条有数量的明细')
    return
  }

  const orderData = {
    customer_name: customerOptions.value.find(item => item.id === manualCustomerId.value)?.customer_name || '',
    order_date: new Date().toISOString().slice(0, 19).replace('T', ' '),
    remark: manualForm.remark,
    items
  }

  selectedReview.value.manual_order = orderData
  selectedCustomerId.value = manualCustomerId.value
  manualDialogVisible.value = false
}

const onTableKeydown = (e) => {
  const { key } = e
  if (!['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Tab', 'Enter'].includes(key)) return
  const el = e.target
  const td = el.closest('td')
  if (!td) return
  const tr = td.closest('tr')
  if (!tr) return
  const tbody = tr.closest('tbody')
  if (!tbody) return
  const rows = [...tbody.rows]
  const cells = [...tr.cells]
  const rowIdx = rows.indexOf(tr)
  const colIdx = cells.indexOf(td)
  let nextRow = rowIdx
  let nextCol = colIdx
  if (key === 'ArrowUp') { nextRow = Math.max(0, rowIdx - 1); e.preventDefault() }
  else if (key === 'ArrowDown' || key === 'Enter') { nextRow = Math.min(rows.length - 1, rowIdx + 1); e.preventDefault() }
  else if (key === 'ArrowLeft') { nextCol = Math.max(0, colIdx - 1); e.preventDefault() }
  else if (key === 'ArrowRight' || key === 'Tab') { nextCol = Math.min(cells.length - 1, colIdx + 1); e.preventDefault() }
  const targetTd = rows[nextRow]?.cells[nextCol]
  if (!targetTd) return
  const input = targetTd.querySelector('input')
  if (input) { input.focus(); input.select?.() }
}

const fetchProductOptions = async () => {
  try {
    const res = await getProductOptions()
    productOptionsRaw.value = res?.data || []
  } catch { productOptionsRaw.value = [] }
}

onMounted(async () => {
  await Promise.all([fetchCustomers(), fetchProductOptions()])
  await fetchReviews()
  _connectSSE()
})

onActivated(() => {
  // keep-alive 场景下重新激活时刷新客户列表（客户可能已新增/修改）
  fetchCustomers()
})

onBeforeUnmount(() => {
  _disconnectSSE()
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

/* ===== 导航 ===== */
.nav-index {
  font-size: 13px;
  color: var(--lark-text-secondary);
  min-width: 60px;
  text-align: center;
}

.detail-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ===== 详情面板 ===== */
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

.detail-uid {
  font-size: 12px;
  color: #909399;
  font-family: 'Courier New', monospace;
  margin-left: 8px;
  background: #f4f4f5;
  padding: 1px 6px;
  border-radius: 3px;
}

/* 中间内容区 */
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
}

.chat-panel > .panel-label,
.compare-right > .panel-label {
  background: var(--lark-bg-base, #fff);
}

/* ===== 左侧 Tabs ===== */
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

/* 信息来源 */
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
  user-select: none;
}

.source-preview-img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  border-radius: 4px;
  transition: transform 0.05s ease-out;
  will-change: transform;
}

.source-text {
  font-size: 13px;
  color: #333;
  white-space: pre-wrap;
  line-height: 1.6;
}

.source-file-info {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: #67c23a;
}

/* 待确认 tab */
.tab-label-badge {
  position: relative;
  display: inline-block;
}

.tab-label-badge .red-dot {
  position: absolute;
  top: -2px;
  right: -8px;
  width: 7px;
  height: 7px;
  background: #f56c6c;
  border-radius: 50%;
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
  margin-bottom: 8px;
  line-height: 1.5;
}

/* ===== 微信风格聊天记录 ===== */

.chat-panel {
  background: #fff;
  padding: 0 10px 0 0 !important;
}

.chat-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  color: var(--lark-text-secondary);
  font-size: 13px;
  padding: 24px 0;
}

/* 时间分隔线 */
.chat-time-sep {
  text-align: center;
  font-size: 11px;
  color: #999;
  margin: 12px 0 8px;
  user-select: none;
}

/* 单条消息 */
.chat-msg {
  margin-bottom: 12px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}

.chat-msg.is-bot {
  align-items: flex-end;
}

/* 发送者行 */
.chat-sender-line {
  font-size: 12px;
  color: #888;
  margin-bottom: 4px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.chat-sender-via {
  color: #aaa;
  margin-left: 2px;
}

.chat-tag {
  flex-shrink: 0;
  font-size: 10px !important;
  height: 18px !important;
  line-height: 16px !important;
  padding: 0 4px !important;
}

/* 气泡 */
.chat-bubble {
  display: inline-block;
  max-width: 85%;
  padding: 8px 12px;
  border-radius: 6px;
  background: #f0f0f0;
  font-size: 13px;
  color: #1d2129;
  line-height: 1.5;
  word-break: break-word;
  position: relative;
  box-shadow: 0 1px 2px rgba(0,0,0,0.06);
}

.chat-bubble.bubble-bot {
  background: #C9E7FF;
  color: #1a1a1a;
}

.chat-bubble.bubble-trigger {
}

.chat-msg.is-trigger .chat-sender-line {
  color: #409eff;
  font-weight: 600;
}

.chat-msg.is-review .chat-sender-line {
  color: #67c23a;
}

.chat-text {
  white-space: pre-wrap;
}

.chat-bubble:has(.chat-inline-image),
.chat-bubble:has(.chat-img-placeholder) {
  padding: 3px;
  background: transparent;
  box-shadow: none;
}

.chat-inline-image {
  max-width: 100px;
  border-radius: 4px;
  cursor: pointer;
  display: block;
}

.chat-img-placeholder {
  width: 90px;
  height: 120px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  color: #b0b0b0;
  font-size: 11px;
  background: #e8e8e8;
  border-radius: 4px;
}

.chat-img-placeholder .placeholder-icon {
  font-size: 24px;
  color: #c0c0c0;
}

.chat-file-wrap {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #67c23a;
  font-size: 13px;
}

.chat-file-link {
  color: #409eff;
  text-decoration: none;
  cursor: pointer;
}

.chat-file-link:hover {
  text-decoration: underline;
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

.order-table .select-col .cell {
  padding: 0 !important;
  height: 100%;
}

.order-table .cell-native-select {
  width: 100%;
  height: 100%;
  border: none;
  outline: none;
  background: transparent;
  text-align: center;
  font-size: 13px;
  color: #303133;
  padding: 0 4px;
  box-sizing: border-box;
  cursor: pointer;
  -webkit-appearance: none;
  -moz-appearance: none;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%23c0c4cc'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 4px center;
  background-size: 8px 5px;
  padding-right: 16px;
}

.order-table .cell-native-select:focus {
  background-color: var(--lark-primary-light, #ecf5ff);
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%23409eff'/%3E%3C/svg%3E");
}

.order-table .cell-native-select option {
  padding: 4px 8px;
}

.order-table .cell-input {
  width: 100%;
  height: 100%;
  border: none;
  outline: none;
  background: transparent;
  text-align: center;
  font-size: 13px;
  color: #303133;
  padding: 0;
  box-sizing: border-box;
  -moz-appearance: textfield;
}

.order-table .cell-input::-webkit-inner-spin-button,
.order-table .cell-input::-webkit-outer-spin-button {
  -webkit-appearance: none;
  margin: 0;
}

.order-table .cell-input:focus {
  background: var(--lark-primary-light, #ecf5ff);
}

.order-table .cell-input.cell-disabled {
  background: #f0f0f0;
  color: #c0c4cc;
  cursor: not-allowed;
}

.order-table .size-col .cell {
  padding: 0 !important;
  height: 100%;
}

.order-table .total-col .cell {
  padding: 0 !important;
}

.order-table .cell-total {
  font-weight: 600;
  color: #303133;
}


.edit-form-area {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.edit-form-actions {
  display: flex;
  gap: 8px;
  padding: 8px 0 0;
  flex-shrink: 0;
  border-top: 1px solid var(--lark-border-light, #ebeef5);
  margin-top: 6px;
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

/* 手动改单弹窗 */
.manual-split {
  display: flex;
  gap: 16px;
  min-height: 50vh;
}

.manual-preview {
  width: 300px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  border-right: 1px solid #eee;
  padding-right: 16px;
}

.manual-preview-label {
  font-size: 13px;
  font-weight: 600;
  color: #666;
  margin-bottom: 8px;
}

.manual-preview-body {
  flex: 1;
  overflow-y: auto;
  scrollbar-width: none;
}

.manual-preview-body::-webkit-scrollbar {
  display: none;
}

.manual-preview-img {
  width: 100%;
  border-radius: 4px;
  cursor: pointer;
}

.manual-preview-text {
  font-size: 13px;
  color: #333;
  white-space: pre-wrap;
  line-height: 1.6;
}

.manual-form {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.manual-top-row {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 12px;
}

.manual-table .cell-select {
  width: 100%;
}

.manual-table .cell-number {
  width: 100%;
}

.manual-table .cell-number .el-input__inner {
  text-align: center;
  padding: 0 2px;
}

.manual-actions {
  margin-top: 8px;
}

.dialog-footer {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
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
