<template>
  <div class="lark-unshipped">
    <div class="lark-page-header">
      <h2 class="header-title">待发货报表</h2>
      <p class="header-desc">查询本地同步的未发货订单明细（定时从 ERP 同步）</p>
    </div>

    <div class="lark-table-panel">
      <!-- 工具栏 -->
      <div class="lark-toolbar">
        <div class="toolbar-left">
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            value-format="YYYY-MM-DD"
            style="width: 260px"
            :shortcuts="dateShortcuts"
          />
          <el-input
            v-model="filter.customer_id"
            placeholder="客户编号"
            clearable
            style="width: 140px"
            @keyup.enter="handleSearch"
          />
          <el-input
            v-model="filter.product_no"
            placeholder="货号"
            clearable
            :prefix-icon="Search"
            style="width: 140px"
            @keyup.enter="handleSearch"
          />
          <el-button type="primary" :icon="Search" @click="handleSearch">查询</el-button>
        </div>
        <div class="toolbar-right">
          <el-button :icon="Refresh" @click="handleSync" :loading="syncing">同步数据</el-button>
          <el-button :icon="Download" @click="handleExport" :disabled="rows.length === 0">导出 CSV</el-button>
        </div>
      </div>

      <!-- 统计 -->
      <div class="summary-bar" v-if="total > 0">
        <span class="summary-item">共 <strong>{{ total }}</strong> 条记录</span>
        <span class="summary-item">未发货总数 <strong>{{ summary.total_unshipped_qty }}</strong></span>
        <span class="summary-item">未发货总金额 <strong>¥{{ Number(summary.total_unshipped_amount || 0).toFixed(2) }}</strong></span>
        <span class="summary-item">订单总数 <strong>{{ summary.total_order_qty }}</strong></span>
        <span class="summary-item">已发货 <strong>{{ summary.total_shipped_qty }}</strong></span>
      </div>

      <!-- 批量操作 -->
      <div class="batch-bar" v-if="selectedRows.length > 0">
        <span>已选 <strong>{{ selectedRows.length }}</strong> 条</span>
        <el-button type="danger" size="small" @click="handleBatchCancel" :loading="batchLoading">批量取消</el-button>
        <el-button type="success" size="small" @click="handleBatchRestore" :loading="batchLoading">批量恢复</el-button>
      </div>

      <!-- 表格 -->
      <el-table
        ref="tableRef"
        :data="rows"
        v-loading="loading"
        stripe
        border
        class="lark-table"
        @selection-change="onSelectionChange"
        :default-sort="{ prop: 'order_date', order: 'descending' }"
        max-height="calc(100vh - 320px)"
      >
        <el-table-column type="selection" width="40" align="center" />
        <el-table-column type="index" label="#" width="45" align="center" />
        <el-table-column label="订单号" prop="order_no" width="140" show-overflow-tooltip>
          <template #default="{ row }">
            <router-link v-if="row.order_no" :to="`/sales/${encodeURIComponent(row.order_no)}`" class="link-text">{{ row.order_no }}</router-link>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="下单日期" prop="order_date" width="100" align="center" sortable />
        <el-table-column label="客户编号" prop="customer_id" width="100" show-overflow-tooltip />
        <el-table-column label="品牌" prop="brand" width="80" show-overflow-tooltip />
        <el-table-column label="货号" prop="product_no" width="120" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="product-no" @click.stop="copyText(row.product_no)">{{ row.product_no || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="品名" prop="product_name" min-width="140" show-overflow-tooltip />
        <el-table-column label="颜色" prop="color" width="80" show-overflow-tooltip />
        <el-table-column label="订单数" prop="order_qty" width="75" align="right" sortable>
          <template #default="{ row }">{{ fmtQty(row.order_qty) }}</template>
        </el-table-column>
        <el-table-column label="已发货" prop="shipped_qty" width="75" align="right">
          <template #default="{ row }">{{ fmtQty(row.shipped_qty) }}</template>
        </el-table-column>
        <el-table-column label="退货数" prop="returned_qty" width="75" align="right">
          <template #default="{ row }">
            <span :class="{ 'qty-warn': row.returned_qty > 0 }">{{ fmtQty(row.returned_qty) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="未发货" prop="unshipped_qty" width="75" align="right" sortable>
          <template #default="{ row }">
            <span class="qty-highlight">{{ fmtQty(row.unshipped_qty) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="库存数" prop="stock_qty" width="75" align="right">
          <template #default="{ row }">
            <span :class="{ 'qty-negative': row.stock_qty < 0 }">{{ fmtQty(row.stock_qty) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="未发尺码" min-width="200">
          <template #default="{ row }">
            <div v-if="row.unshipped_sizes && row.unshipped_sizes.length > 0" class="size-tags">
              <el-tag v-for="s in row.unshipped_sizes" :key="s.size" size="small" effect="plain" class="size-tag">
                {{ s.size }}: {{ s.qty }}
              </el-tag>
            </div>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="制单人" prop="creator" width="80" show-overflow-tooltip />
        <el-table-column label="备注" prop="remark" width="120" show-overflow-tooltip />
      </el-table>

      <!-- 分页 -->
      <div class="lark-pagination" v-if="total > 0">
        <el-pagination
          v-model:current-page="filter.page"
          v-model:page-size="filter.rows"
          :page-sizes="[100, 200, 500, 1000]"
          :total="total"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="fetchReport"
          @current-change="fetchReport"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Download, Refresh } from '@element-plus/icons-vue'
import { getUnshippedReport, cancelUnshipped, restoreUnshipped, syncUnshippedReport } from '@/api/unshippedReport'

const loading = ref(false)
const batchLoading = ref(false)
const syncing = ref(false)
const rows = ref([])
const total = ref(0)
const summary = ref({})
const selectedRows = ref([])
const tableRef = ref(null)

// 默认查最近90天
const today = new Date()
const ninetyDaysAgo = new Date(today)
ninetyDaysAgo.setDate(today.getDate() - 90)
const fmt = (d) => d.toISOString().slice(0, 10)

const dateRange = ref([fmt(ninetyDaysAgo), fmt(today)])

const filter = reactive({
  customer_id: '',
  product_no: '',
  page: 1,
  rows: 200,
})

const dateShortcuts = [
  { text: '最近30天', value: () => { const e = new Date(); const s = new Date(); s.setDate(e.getDate() - 30); return [s, e] } },
  { text: '最近90天', value: () => { const e = new Date(); const s = new Date(); s.setDate(e.getDate() - 90); return [s, e] } },
  { text: '最近180天', value: () => { const e = new Date(); const s = new Date(); s.setDate(e.getDate() - 180); return [s, e] } },
  { text: '最近1年', value: () => { const e = new Date(); const s = new Date(); s.setFullYear(e.getFullYear() - 1); return [s, e] } },
]


function fmtQty(v) {
  const n = Number(v) || 0
  return n === 0 ? '-' : Math.round(n)
}

function handleSearch() {
  filter.page = 1
  fetchReport()
}

async function fetchReport() {
  loading.value = true
  try {
    const params = {
      page: filter.page,
      page_size: filter.rows,
    }
    if (dateRange.value && dateRange.value.length === 2) {
      params.dates = dateRange.value[0]
      params.datee = dateRange.value[1]
    }
    if (filter.customer_id) params.customer_id = filter.customer_id
    if (filter.product_no) params.product_no = filter.product_no

    const res = await getUnshippedReport(params)
    const d = res.data || {}
    rows.value = d.list || []
    total.value = d.total || 0
    summary.value = d.summary || {}
  } catch (e) {
    console.error('获取待发货报表失败:', e)
    rows.value = []
    total.value = 0
    summary.value = {}
  } finally {
    loading.value = false
  }
}

async function handleSync() {
  syncing.value = true
  try {
    await syncUnshippedReport(360)
    ElMessage.success('同步已启动，数据将在后台更新')
    setTimeout(() => fetchReport(), 3000)
  } catch (e) {
    ElMessage.error('同步触发失败: ' + (e?.message || '未知错误'))
  } finally {
    syncing.value = false
  }
}

function onSelectionChange(selection) {
  selectedRows.value = selection
}

async function handleBatchCancel() {
  const ids = selectedRows.value.map(r => r.erp_row_id).filter(Boolean)
  if (ids.length === 0) return
  try {
    await ElMessageBox.confirm(`确认取消 ${ids.length} 条未发货记录？`, '批量取消', { type: 'warning' })
  } catch { return }
  batchLoading.value = true
  try {
    await cancelUnshipped(ids)
    ElMessage.success(`已取消 ${ids.length} 条记录`)
    fetchReport()
  } catch (e) {
    ElMessage.error('取消失败: ' + (e?.message || '未知错误'))
  } finally {
    batchLoading.value = false
  }
}

async function handleBatchRestore() {
  const ids = selectedRows.value.map(r => r.erp_row_id).filter(Boolean)
  if (ids.length === 0) return
  try {
    await ElMessageBox.confirm(`确认恢复 ${ids.length} 条记录？`, '批量恢复', { type: 'warning' })
  } catch { return }
  batchLoading.value = true
  try {
    await restoreUnshipped(ids)
    ElMessage.success(`已恢复 ${ids.length} 条记录`)
    fetchReport()
  } catch (e) {
    ElMessage.error('恢复失败: ' + (e?.message || '未知错误'))
  } finally {
    batchLoading.value = false
  }
}

function handleExport() {
  if (rows.value.length === 0) return
  const headers = ['订单号', '下单日期', '客户编号', '客户订单号', '品牌', '货号', '品名', '颜色', '订单数', '已发货', '退货数', '未发货', '未发金额', '库存数', '单价', '未发尺码', '制单人', '备注']
  const csvRows = rows.value.map(r => [
    r.order_no, r.order_date, r.customer_id, r.customer_order_no || '',
    r.brand || '', r.product_no, r.product_name || '', r.color || '',
    r.order_qty || 0, r.shipped_qty || 0, r.returned_qty || 0, r.unshipped_qty || 0,
    r.unshipped_amount || 0, r.stock_qty || 0, r.price || 0,
    (r.unshipped_sizes || []).map(s => `${s.size}:${s.qty}`).join(' '),
    r.creator || '', r.remark || '',
  ])
  const BOM = '\uFEFF'
  const csv = BOM + [headers.join(','), ...csvRows.map(r => r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(','))].join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `待发货报表_${dateRange.value[0]}_${dateRange.value[1]}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

function copyText(text) {
  if (!text) return
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(() => ElMessage.success('已复制')).catch(() => fallbackCopy(text))
  } else {
    fallbackCopy(text)
  }
}

function fallbackCopy(text) {
  const ta = document.createElement('textarea')
  ta.value = text
  ta.style.position = 'fixed'
  ta.style.left = '-9999px'
  document.body.appendChild(ta)
  ta.select()
  try { document.execCommand('copy'); ElMessage.success('已复制') } catch { ElMessage.error('复制失败') }
  document.body.removeChild(ta)
}

onMounted(() => {
  fetchReport()
})
</script>

<style scoped>
.lark-unshipped {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.lark-page-header { margin-bottom: 4px; }

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

.lark-table-panel {
  background: var(--lark-bg-base);
  border-radius: var(--lark-radius-lg);
  padding: 20px 24px;
}

.lark-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 12px;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.summary-bar {
  display: flex;
  gap: 24px;
  padding: 10px 14px;
  background: var(--lark-bg-subtle, #f7f8fa);
  border-radius: var(--lark-radius);
  margin-bottom: 12px;
  font-size: 13px;
  color: var(--lark-text-secondary);
}

.summary-item strong {
  color: var(--lark-text-primary);
  margin: 0 2px;
}

.batch-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 14px;
  background: #ecf5ff;
  border-radius: var(--lark-radius);
  margin-bottom: 12px;
  font-size: 13px;
}

.batch-bar strong {
  color: var(--el-color-primary);
}

.product-no {
  cursor: pointer;
  color: var(--el-color-primary, #409eff);
  font-weight: 500;
}

.link-text {
  color: var(--el-color-primary, #409eff);
  text-decoration: none;
  font-weight: 500;
}

.link-text:hover {
  text-decoration: underline;
}

.qty-highlight {
  color: #e6a23c;
  font-weight: 600;
}

.qty-warn {
  color: #f56c6c;
}

.qty-negative {
  color: #f56c6c;
  font-weight: 600;
}

.amount-text {
  font-weight: 500;
}

.text-muted {
  color: var(--lark-text-disabled);
}

.size-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.size-tag {
  font-size: 12px;
}

.lark-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
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
