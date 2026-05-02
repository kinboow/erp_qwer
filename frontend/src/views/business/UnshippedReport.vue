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
          <el-select
            v-model="filter.customer_id"
            placeholder="选择客户"
            clearable
            filterable
            style="width: 180px"
            @change="handleSearch"
          >
            <el-option
              v-for="c in customerList"
              :key="c.erp_customer_id"
              :label="c.customer_name"
              :value="c.erp_customer_id"
            />
          </el-select>
          <el-input
            v-model="filter.product_no"
            placeholder="货号"
            clearable
            :prefix-icon="Search"
            style="width: 140px"
            @keyup.enter="handleSearch"
          />
          <el-button type="primary" :icon="Search" @click="handleSearch">查询</el-button>
          <el-switch v-model="mergeByOrder" active-text="合并同单" inactive-text="" style="margin-left: 8px" />
          <template v-if="selectedRows.length > 0">
            <el-button type="primary" size="default" :loading="printing" @click="handlePrint(selectedRows)">批量打印 ({{ selectedRows.length }})</el-button>
          </template>
        </div>
        <div class="toolbar-right">
          <el-button :icon="syncing ? undefined : Refresh" @click="handleSync" :loading="syncing">{{ syncing ? `同步中${trigger === 'scheduled' ? '（定时）' : ''}...` : '同步数据' }}</el-button>
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
        <span v-if="selectedRows.length" class="summary-item">已选 <strong>{{ selectedRows.length }}</strong> 条</span>
      </div>

      <!-- 表格（普通视图） -->
      <el-table
        v-if="!mergeByOrder"
        ref="tableRef"
        :data="rows"
        v-loading="loading"
        stripe
        border
        class="lark-table"
        @selection-change="onSelectionChange"
        :default-sort="{ prop: 'order_date', order: 'descending' }"
        style="flex: 1"
      >
        <el-table-column type="selection" width="40" align="center" />
        <el-table-column type="index" label="#" width="45" align="center" />
        <el-table-column label="订单号" prop="order_no" width="140" show-overflow-tooltip>
          <template #default="{ row }">
            <router-link v-if="row.order_no" :to="`/sales/${encodeURIComponent(row.order_no)}`" class="link-text">{{ row.order_no }}</router-link>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="下单日期" prop="order_date" width="120" align="center" sortable />
        <el-table-column label="客户名称" prop="customer_id" width="120" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.customer_name || row.customer_id || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="货号" prop="product_no" width="120" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="product-no" @click.stop="copyText(row.product_no)">{{ row.product_no || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="颜色" prop="color" width="80" show-overflow-tooltip />
        <el-table-column label="下单数" prop="order_qty" width="90" align="right" sortable>
          <template #default="{ row }">{{ fmtQty(row.order_qty) }}</template>
        </el-table-column>
        <el-table-column label="未发货数" prop="unshipped_qty" width="110" align="right" sortable>
          <template #default="{ row }">
            <span class="qty-highlight">{{ fmtQty(row.unshipped_qty) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="未发尺码" min-width="150">
          <template #default="{ row }">
            <div v-if="row.unshipped_sizes && row.unshipped_sizes.length > 0" class="size-tags">
              <el-tag v-for="s in row.unshipped_sizes" :key="s.size" size="small" effect="plain" class="size-tag">
                {{ s.size }}: {{ s.qty }}
              </el-tag>
            </div>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" prop="remark" width="120" show-overflow-tooltip />
        <el-table-column label="操作" width="120" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="handleView(row)">查看</el-button>
            <el-button link type="primary" size="small" @click="handlePrint([row])">打印</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 表格（合并同单视图） -->
      <el-table
        v-else
        ref="tableRef"
        :data="mergedRows"
        v-loading="loading"
        border
        class="lark-table merged-table"
        row-key="order_no"
        style="flex: 1"
      >
        <el-table-column type="expand">
          <template #default="{ row: group }">
            <div class="expand-detail">
              <table class="expand-inner-table">
                <thead>
                  <tr>
                    <th>货号</th>
                    <th>颜色</th>
                    <th>下单数</th>
                    <th>未发货数</th>
                    <th>未发尺码</th>
                    <th>备注</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(item, idx) in group.items" :key="idx">
                    <td>
                      <span class="product-no" @click.stop="copyText(item.product_no)">{{ item.product_no || '-' }}</span>
                    </td>
                    <td>{{ item.color || '-' }}</td>
                    <td align="right">{{ fmtQty(item.order_qty) }}</td>
                    <td align="right"><span class="qty-highlight">{{ fmtQty(item.unshipped_qty) }}</span></td>
                    <td>
                      <div v-if="item.unshipped_sizes && item.unshipped_sizes.length" class="size-tags">
                        <el-tag v-for="s in item.unshipped_sizes" :key="s.size" size="small" effect="plain" class="size-tag">{{ s.size }}: {{ s.qty }}</el-tag>
                      </div>
                      <span v-else class="text-muted">-</span>
                    </td>
                    <td>{{ item.remark || '-' }}</td>
                    <td>
                      <el-button link type="primary" size="small" @click="handleView(item)">查看</el-button>
                      <el-button link type="primary" size="small" @click="handlePrint([item])">打印</el-button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </template>
        </el-table-column>
        <el-table-column type="index" label="#" width="50" align="center" />
        <el-table-column label="订单号" prop="order_no" min-width="160" show-overflow-tooltip>
          <template #default="{ row: group }">
            <router-link :to="`/sales/${encodeURIComponent(group.order_no)}`" class="link-text">{{ group.order_no }}</router-link>
          </template>
        </el-table-column>
        <el-table-column label="下单日期" prop="order_date" min-width="120" align="center" sortable />
        <el-table-column label="客户名称" min-width="140" show-overflow-tooltip>
          <template #default="{ row: group }">
            {{ group.customer_name || group.customer_id || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="商品数" min-width="80" align="center">
          <template #default="{ row: group }">
            <el-tag size="small" type="info">{{ new Set(group.items.map(i => i.product_no)).size }} 款</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="总下单数" min-width="100" align="right">
          <template #default="{ row: group }">
            {{ fmtQty(group.total_order_qty) }}
          </template>
        </el-table-column>
        <el-table-column label="总未发货" min-width="100" align="right">
          <template #default="{ row: group }">
            <span class="qty-highlight">{{ fmtQty(group.total_unshipped_qty) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" align="center">
          <template #default="{ row: group }">
            <el-button link type="primary" size="small" @click="handlePrint(group.items)">打印整单</el-button>
          </template>
        </el-table-column>
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
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Download, Refresh, Printer, View } from '@element-plus/icons-vue'
import { getUnshippedReport, cancelUnshipped, restoreUnshipped, syncUnshippedReport, printUnshipped } from '@/api/unshippedReport'
import { getCustomerList } from '@/api/customer'
import { useSyncStatus } from '@/composables/useSyncStatus'

const router = useRouter()

const loading = ref(false)
const batchLoading = ref(false)
const printing = ref(false)
const rows = ref([])
const total = ref(0)
const summary = ref({})
const selectedRows = ref([])
const tableRef = ref(null)
const customerList = ref([])

const mergeByOrder = ref(false)

const filter = reactive({
  customer_id: '',
  product_no: '',
  page: 1,
  rows: 200,
})

const mergedRows = computed(() => {
  const groups = {}
  for (const row of rows.value) {
    const key = row.order_no
    if (!groups[key]) {
      groups[key] = {
        order_no: row.order_no,
        order_date: row.order_date,
        customer_id: row.customer_id,
        customer_name: row.customer_name,
        items: [],
        total_order_qty: 0,
        total_unshipped_qty: 0,
      }
    }
    groups[key].items.push(row)
    groups[key].total_order_qty += Number(row.order_qty) || 0
    groups[key].total_unshipped_qty += Number(row.unshipped_qty) || 0
  }
  return Object.values(groups)
})


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

const { syncing, trigger } = useSyncStatus('unshipped', () => fetchReport())

async function handleSync() {
  if (syncing.value) return
  syncing.value = true
  try {
    const res = await syncUnshippedReport(360)
    if (res.data?.already_syncing) {
      ElMessage.info('未发货报表同步进行中，完成后将自动刷新')
    } else {
      ElMessage.success('同步已启动，完成后将自动刷新')
    }
  } catch {
    ElMessage.error('同步失败，请检查 ERP 配置')
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

function handleView(row) {
  router.push(`/unshipped-report/${row.id}`)
}

async function handlePrint(printRows) {
  if (!printRows || printRows.length === 0) return
  const ids = printRows.map(r => r.id).filter(Boolean)
  if (ids.length === 0) { ElMessage.warning('没有可打印的记录'); return }
  const cName = printRows[0]?.customer_name || ''
  printing.value = true
  try {
    const res = await printUnshipped(ids, cName)
    if (res.code === 200 && res.data?.oss_url) {
      window.open(res.data.oss_url, '_blank')
      ElMessage.success(`待发货单已生成（${res.data.item_count} 条）`)
    } else {
      ElMessage.error(res.message || '生成待发货单失败')
    }
  } catch (e) {
    console.error('打印待发货单失败:', e)
    ElMessage.error('打印失败，请重试')
  } finally {
    printing.value = false
  }
}

function handleExport() {
  if (rows.value.length === 0) return
  const headers = ['订单号', '下单日期', '客户名称', '货号', '颜色', '订单数', '未发货', '未发尺码', '备注']
  const csvRows = rows.value.map(r => [
    r.order_no, r.order_date, r.customer_name || r.customer_id || '',
    r.product_no, r.color || '',
    r.order_qty || 0, r.unshipped_qty || 0,
    (r.unshipped_sizes || []).map(s => `${s.size}:${s.qty}`).join(' '),
    r.remark || '',
  ])
  const BOM = '\uFEFF'
  const csv = BOM + [headers.join(','), ...csvRows.map(r => r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(','))].join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `待发货报表_${new Date().toISOString().slice(0, 10)}.csv`
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

async function fetchCustomers() {
  try {
    const res = await getCustomerList({ page: 1, pageSize: 200 })
    customerList.value = (res.data?.list || []).filter(c => c.erp_customer_id)
  } catch (e) {
    console.error('获取客户列表失败:', e)
  }
}

onMounted(() => {
  fetchCustomers()
  fetchReport()
})
</script>

<style scoped>
.lark-unshipped {
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: 100%;
  overflow: hidden;
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
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
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

/* 合并视图 — 展开内表格 */
.expand-detail {
  padding: 12px 20px 12px 48px;
}

.expand-inner-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.expand-inner-table th,
.expand-inner-table td {
  border: 1px solid var(--lark-border-light, #e5e6eb);
  padding: 8px 10px;
  text-align: left;
}

.expand-inner-table th {
  background: var(--lark-bg-subtle, #f7f8fa);
  font-weight: 600;
  color: var(--lark-text-primary, #1f2329);
  font-size: 12px;
}

.expand-inner-table tr:hover td {
  background: #f5f7fa;
}

:deep(.merged-table .el-table__expanded-cell) {
  padding: 0 !important;
  background: #fafbfc;
}

</style>
