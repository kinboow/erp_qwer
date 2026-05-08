<template>
  <div class="lark-approval">
    <div class="lark-page-header">
      <div class="header-title">审核列表</div>
      <div class="header-desc">查看所有下游客户订单审核记录</div>
    </div>

    <div class="lark-table-panel">
      <!-- 工具栏 -->
      <div class="lark-toolbar">
        <div class="toolbar-left">
          <el-select v-model="filter.reviewStatus" style="width: 130px" @change="handleSearch">
            <el-option label="全部状态" value="" />
            <el-option label="待审核" value="pending" />
            <el-option label="已审核下单" value="approved" />
            <el-option label="已替换旧单" value="replaced" />
            <el-option label="手动录单" value="manual_ordered" />
            <el-option label="废单" value="voided" />
            <el-option label="异常" value="exception" />
          </el-select>
          <template v-if="selectedRows.length > 0">
            <el-button v-if="filter.reviewStatus === 'voided' || filter.reviewStatus === 'exception'" type="primary" size="default" :loading="batchLoading" @click="batchRevertPending">
              批量转为待审核 ({{ selectedRows.length }})
            </el-button>
            <el-button v-if="filter.reviewStatus === 'pending'" type="danger" plain size="default" :loading="batchLoading" @click="batchVoid">
              批量作废 ({{ selectedRows.length }})
            </el-button>
          </template>
        </div>
        <div class="toolbar-right">
          <el-button :icon="Download" size="default" @click="handleExport">导出</el-button>
        </div>
      </div>

      <!-- 统计 -->
      <div class="summary-bar" v-if="total > 0">
        <span class="summary-item">共 <strong>{{ total }}</strong> 条</span>
        <span v-if="selectedRows.length" class="summary-item">已选 <strong>{{ selectedRows.length }}</strong> 条</span>
      </div>

      <!-- 表格 -->
      <el-table
        ref="tableRef"
        :data="list"
        v-loading="loading"
        stripe
        class="lark-table"
        row-key="id"
        highlight-current-row
        @selection-change="onSelectionChange"
      >
        <el-table-column type="selection" width="45" align="center" />
        <el-table-column type="index" label="#" width="50" align="center" />
        <el-table-column prop="review_uid" label="审核单号" width="150" show-overflow-tooltip />
        <el-table-column label="审核状态" width="120" align="center">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.review_status)" size="small">{{ statusText(row.review_status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="customer_name" label="客户" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ row.customer_name || '未匹配客户' }}</template>
        </el-table-column>
        <el-table-column prop="room_name" label="来源群聊" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">{{ row.room_name || '-' }}</template>
        </el-table-column>
        <el-table-column prop="sender_name" label="发送人" width="110" show-overflow-tooltip>
          <template #default="{ row }">{{ row.sender_name || '-' }}</template>
        </el-table-column>
        <el-table-column label="消息类型" width="90" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="msgTagType(row.message_type)" effect="plain">
              {{ msgTypeText(row.message_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="解析内容" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.parsed_order && row.parsed_order.items">
              {{ [...new Set(row.parsed_order.items.map(i => i.product_no || '').filter(Boolean))].length }} 款：
              {{ [...new Set(row.parsed_order.items.map(i => i.product_no || '').filter(Boolean))].slice(0, 3).join('、') }}
              <span v-if="[...new Set(row.parsed_order.items.map(i => i.product_no || '').filter(Boolean))].length > 3">…</span>
            </span>
            <span v-else class="text-muted">无解析结果</span>
          </template>
        </el-table-column>
        <el-table-column prop="operator_name" label="操作人" width="100" align="center" show-overflow-tooltip>
          <template #default="{ row }">{{ row.operator_name || '-' }}</template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="160" align="center" fixed="right">
          <template #default="{ row }">
            <template v-if="row.review_status === 'pending'">
              <el-button type="primary" link size="small" @click.stop="goReview(row)">去审核</el-button>
              <el-button type="danger" link size="small" :loading="row._voiding" @click.stop="handleVoid(row)">作废</el-button>
            </template>
            <template v-else-if="row.review_status === 'voided' || row.review_status === 'exception'">
              <el-button type="primary" link size="small" :loading="row._reverting" @click.stop="handleRevert(row)">转为待审核</el-button>
            </template>
            <template v-else>
              <el-button type="default" link size="small" @click.stop="goReview(row)">查看</el-button>
            </template>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="lark-pagination">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :total="total"
          :page-sizes="[20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSearch"
          @current-change="fetchData"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, onBeforeUnmount, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download } from '@element-plus/icons-vue'
import { getReviewList, voidReview, revertPending } from '@/api/downstreamOrders'

const router = useRouter()
const loading = ref(false)
const batchLoading = ref(false)
const list = ref([])
const total = ref(0)
const selectedRows = ref([])
const tableRef = ref(null)

const filter = reactive({
  reviewStatus: 'pending'
})

const pagination = reactive({
  page: 1,
  pageSize: 20
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

const msgTypeText = (type) => {
  const map = {
    text: '文字',
    image: '图片',
    file: '文件',
    video: '视频',
    voice: '语音',
    link: '链接',
    gif: 'GIF',
    location: '位置',
    card: '名片',
    miniprogram: '小程序',
    batch: '批量识别',
  }
  return map[type] || type || '未知'
}

const msgTagType = (type) => {
  const map = { image: 'warning', file: '', video: 'info', text: 'info' }
  return map[type] || 'info'
}

const formatDate = (value) => {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN')
}

const onSelectionChange = (rows) => {
  selectedRows.value = rows
}

const handleSearch = () => {
  pagination.page = 1
  fetchData()
}

const fetchData = async () => {
  loading.value = true
  try {
    const res = await getReviewList({
      page: pagination.page,
      pageSize: pagination.pageSize,
      review_status: filter.reviewStatus || undefined,
      sort: filter.reviewStatus === 'pending' ? 'asc' : 'desc'
    }, { silentError: true })
    list.value = res?.data?.list || []
    total.value = res?.data?.total || 0
    selectedRows.value = []
  } catch {
    list.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

const goReview = (row) => {
  router.push({ path: '/downstream-order-reviews', query: { id: row.id } })
}

const handleVoid = async (row) => {
  try {
    await ElMessageBox.confirm('确定要将此审核单作废吗？', '作废确认', { type: 'warning' })
  } catch { return }
  row._voiding = true
  try {
    await voidReview(row.id, { review_note: '审核列表批量作废' })
    ElMessage.success('已作废')
    await fetchData()
  } catch (e) {
    ElMessage.error('作废失败: ' + (e?.message || '未知错误'))
  } finally {
    row._voiding = false
  }
}

const handleRevert = async (row) => {
  row._reverting = true
  try {
    await revertPending(row.id)
    ElMessage.success('已转为待审核')
    await fetchData()
  } catch (e) {
    ElMessage.error('操作失败: ' + (e?.message || '未知错误'))
  } finally {
    row._reverting = false
  }
}

const batchVoid = async () => {
  const ids = selectedRows.value.filter(r => r.review_status === 'pending').map(r => r.id)
  if (ids.length === 0) { ElMessage.warning('没有可作废的记录'); return }
  try {
    await ElMessageBox.confirm(`确定要批量作废 ${ids.length} 条记录吗？`, '批量作废', { type: 'warning' })
  } catch { return }
  batchLoading.value = true
  let ok = 0; let fail = 0
  for (const id of ids) {
    try { await voidReview(id, { review_note: '审核列表批量作废' }); ok++ } catch { fail++ }
  }
  batchLoading.value = false
  ElMessage.success(`批量作废完成：成功 ${ok} 条${fail ? `，失败 ${fail} 条` : ''}`)
  await fetchData()
}

const batchRevertPending = async () => {
  const ids = selectedRows.value.filter(r => r.review_status === 'voided' || r.review_status === 'exception').map(r => r.id)
  if (ids.length === 0) { ElMessage.warning('没有可转为待审核的记录'); return }
  try {
    await ElMessageBox.confirm(`确定要将 ${ids.length} 条记录转为待审核吗？`, '批量转为待审核', { type: 'info' })
  } catch { return }
  batchLoading.value = true
  let ok = 0; let fail = 0
  for (const id of ids) {
    try { await revertPending(id); ok++ } catch { fail++ }
  }
  batchLoading.value = false
  ElMessage.success(`批量转为待审核完成：成功 ${ok} 条${fail ? `，失败 ${fail} 条` : ''}`)
  await fetchData()
}

const handleExport = () => {
  const rows = selectedRows.value.length > 0 ? selectedRows.value : list.value
  if (rows.length === 0) { ElMessage.warning('没有可导出的数据'); return }
  const headers = ['审核单号', '审核状态', '客户', '来源群聊', '发送人', '消息类型', '操作人', '创建时间', '备注']
  const csvRows = rows.map(r => [
    r.review_uid || '',
    statusText(r.review_status),
    r.customer_name || '',
    r.room_name || '',
    r.sender_name || '',
    msgTypeText(r.message_type),
    r.operator_name || '',
    formatDate(r.created_at),
    (r.review_note || '').replace(/"/g, '""')
  ])
  const bom = '\uFEFF'
  const csv = bom + [headers, ...csvRows].map(r => r.map(c => `"${c}"`).join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `审核列表_${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success(`已导出 ${rows.length} 条`)
}

let _eventSource = null

const _connectSSE = () => {
  _disconnectSSE()
  _eventSource = new EventSource('/api/downstream-orders/reviews/stream')
  _eventSource.onmessage = async (e) => {
    try {
      const payload = JSON.parse(e.data)
      if (payload.event === 'new_review') {
        await fetchData()
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

onMounted(() => {
  fetchData()
  _connectSSE()
})

onBeforeUnmount(() => {
  _disconnectSSE()
})
</script>

<style scoped>
.lark-approval {
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
}

.summary-bar strong {
  color: var(--lark-text-primary, #1f2329);
}

.lark-table {
  flex: 1;
  min-height: 0;
}

.text-muted {
  color: #c0c4cc;
  font-style: italic;
}

.lark-pagination {
  margin-top: 14px;
  display: flex;
  justify-content: flex-end;
  flex-shrink: 0;
}
</style>
