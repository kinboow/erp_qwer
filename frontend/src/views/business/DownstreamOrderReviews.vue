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
            <el-option label="异常" value="exception" />
          </el-select>
          <span class="list-total">{{ pagination.total }} 条</span>
        </div>

        <el-scrollbar class="list-scroll" ref="listScrollRef" @scroll="onListScroll">
          <div
            v-for="item in reviewList"
            :key="item.id"
            class="review-list-item"
            :class="{ active: selectedReview?.id === item.id }"
            @click="selectReview(item)"
          >
            <div class="review-item-head">
              <span class="room-name">{{ item.customer_name || '未匹配客户' }}</span>
              <el-tag size="small" :type="statusTagType(item.review_status)">{{ statusText(item.review_status) }}</el-tag>
            </div>
            <div class="review-item-meta">
              <span>{{ item.sender_name || '' }}</span>
              <span>{{ formatDate(item.created_at) }}</span>
            </div>
          </div>
          <div v-if="reviewLoading && reviewList.length > 0" class="list-loading-more">
            <el-icon class="is-loading"><Loading /></el-icon> 加载中...
          </div>
          <div v-if="!reviewLoading && noMoreReviews && reviewList.length > 0" class="list-no-more">没有更多了</div>
          <el-empty v-if="!reviewLoading && reviewList.length === 0" description="暂无数据" :image-size="64" />
        </el-scrollbar>
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
              <span v-if="selectedReview.review_uid" class="detail-uid">{{ selectedReview.review_uid }}</span>
            </div>
            <el-button class="lark-btn-secondary" size="default" @click="handleReparse" :loading="actionLoading">重新解析</el-button>
          </div>

          <!-- 中间对比区：左原始消息 / 右解析结果 -->
          <div class="detail-body">
            <div class="compare-grid">
              <div class="compare-left chat-panel" ref="chatContainerRef">
                <div class="panel-label">群聊上下文</div>
                <div v-if="contextLoading" class="chat-loading">
                  <el-icon class="is-loading"><Loading /></el-icon> 加载聊天记录...
                </div>
                <template v-else-if="contextMessages.length > 0">
                  <template v-for="(msg, idx) in contextMessages" :key="msg.id">
                    <!-- 时间分隔线 -->
                    <div v-if="shouldShowTime(idx)" class="chat-time-sep">{{ formatChatTime(msg.created_at) }}</div>
                    <!-- 消息 -->
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
                <template v-if="currentOrder">
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
              <template v-if="selectedReview.review_status === 'pending'">
                <el-button type="primary" :loading="actionLoading" @click="handleApprove">审核下单</el-button>
                <el-button type="warning" :loading="actionLoading" @click="handleReplace">替换旧单</el-button>
                <el-button type="success" :loading="actionLoading" @click="openManualDialog">手动改单</el-button>
                <el-button type="danger" plain :loading="actionLoading" @click="handleVoid">废单</el-button>
              </template>
              <template v-else-if="selectedReview.review_status === 'voided' || selectedReview.review_status === 'exception'">
                <el-button type="primary" :loading="actionLoading" @click="handleRevertPending">转为待审核</el-button>
              </template>
            </div>
          </div>
        </template>
        <el-empty v-else description="请选择左侧消息查看详情" class="detail-empty" />
      </div>
    </div>

    <el-dialog v-model="manualDialogVisible" title="手动改单" width="860px" destroy-on-close>
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
          <el-button type="primary" @click="submitManualOrder">提交修改</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, ElImageViewer } from 'element-plus'
import { Loading, Picture, Document, WarningFilled } from '@element-plus/icons-vue'
import { getCustomerList } from '@/api/customer'
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
const noMoreReviews = ref(false)
const listScrollRef = ref(null)

const contextLoading = ref(false)
const contextMessages = ref([])
const triggerMsgId = ref(null)
const reviewMsgIds = ref([])
const chatContainerRef = ref(null)
const previewImageUrl = ref('')

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
    const res = await getCustomerList({ page: 1, pageSize: 500 }, { silentError: true })
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
        await fetchReviews()
      }
    } catch {}
  }
  _eventSource.onerror = () => {
    _disconnectSSE()
    setTimeout(_connectSSE, 5000)
  }
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
      review_status: filters.review_status || undefined
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
        const targetId = selectedReview.value?.id
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

const loadMoreReviews = () => {
  if (noMoreReviews.value || reviewLoading.value) return
  pagination.page++
  fetchReviews(true)
}

const onListScroll = ({ scrollTop }) => {
  const wrap = listScrollRef.value?.wrapRef
  if (!wrap) return
  if (wrap.scrollHeight - scrollTop - wrap.clientHeight < 80) {
    loadMoreReviews()
  }
}

const selectReview = async (item) => {
  const res = await getReviewDetail(item.id)
  selectedReview.value = res.data
  selectedCustomerId.value = res.data.customer_id || null
  reviewNote.value = res.data.review_note || ''
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
    ElMessage.success(`审核下单成功，ERP单号: ${d.order_no || '-'}，${d.message || ''}`)
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
    ElMessage.success(`替换旧单成功，新ERP单号: ${d.order_no || '-'}${replacedInfo}`)
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

const submitManualOrder = () => {
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
    ElMessage.warning('请至少填写一条完整的明细')
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

onMounted(async () => {
  await fetchCustomers()
  await fetchReviews()
  _connectSSE()
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

/* ===== 左侧列表面板 ===== */
.list-panel {
  width: 290px;
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

.list-loading-more,
.list-no-more {
  text-align: center;
  font-size: 12px;
  color: #999;
  padding: 10px 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
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
  grid-template-columns: 340px 1fr;
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
  background: #95ec69;
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
