<template>
  <div class="lark-sales">
    <div class="lark-page-header">
      <div class="header-title">销售订单</div>
      <div class="header-desc">查看从 ERP 同步到本地的销售订单数据</div>
    </div>

    <div class="lark-table-panel">
      <!-- 工具栏 -->
      <div class="lark-toolbar">
        <div class="toolbar-left">
          <el-select v-model="filter.state" placeholder="订单状态" clearable style="width: 120px;" @change="handleSearch">
            <el-option label="全部" value="" />
            <el-option label="未审核" value="0" />
            <el-option label="已审核" value="1" />
          </el-select>
          <el-date-picker
            v-model="filter.dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            value-format="YYYY-MM-DD"
            style="width: 260px;"
            @change="handleSearch"
          />
          <div class="lark-search-input-wrap">
            <el-icon class="search-icon"><Search /></el-icon>
            <input
              v-model="filter.keyword"
              class="lark-input"
              placeholder="搜索订单号 / 客户名"
              @input="debouncedSearch"
            />
          </div>
        </div>
        <div class="toolbar-right">
          <el-button :icon="syncing ? undefined : Refresh" @click="handleSync" :loading="syncing">{{ syncing ? '同步订单中...' : '同步销售订单' }}</el-button>
        </div>
      </div>

      <!-- 统计摘要 -->
      <div class="summary-bar" v-if="total > 0">
        <span class="summary-item">共 <strong>{{ total }}</strong> 条订单</span>
        <span class="summary-item">总数量 <strong>{{ summaryQty }}</strong></span>
        <span class="summary-item">总金额 <strong>¥{{ summaryAmount }}</strong></span>
      </div>

      <!-- 订单表格 -->
      <el-table
        :data="orders"
        v-loading="loading"
        stripe
        class="lark-table"
        row-key="order_no"
      >
        <el-table-column type="index" label="序号" width="60" align="center" />
        <el-table-column label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.state === 1 ? 'success' : 'warning'" size="small">
              {{ row.state === 1 ? '已审核' : '未审核' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="印次" prop="print_count" width="70" align="center" />
        <el-table-column label="单号" prop="order_no" width="160">
          <template #default="{ row }">
            <span class="order-no copyable" @click.stop="copyOrderNo(row.order_no)" title="点击复制">{{ row.order_no }}</span>
          </template>
        </el-table-column>
        <el-table-column label="订单日期" prop="order_date" width="120" />
        <el-table-column label="客户名称" prop="customer_name" min-width="140" show-overflow-tooltip />
        <el-table-column label="客户电话" prop="customer_tel" width="130" show-overflow-tooltip />
        <el-table-column label="客户地址" prop="customer_addr" min-width="160" show-overflow-tooltip />
        <el-table-column label="货号" prop="product_no" width="130" show-overflow-tooltip />
        <el-table-column label="总数量" prop="total_qty" width="80" align="right" />
        <el-table-column label="备注" prop="remark" min-width="120" show-overflow-tooltip />
        <el-table-column label="操作" width="90" fixed="right" align="center">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="viewDetail(row)">查看详情</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="lark-pagination" v-if="total > 0">
        <el-pagination
          v-model:current-page="filter.page"
          v-model:page-size="filter.page_size"
          :page-sizes="[20, 50, 100]"
          :total="total"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="fetchOrders"
          @current-change="fetchOrders"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Search, Refresh } from '@element-plus/icons-vue'
import { getSalesOrders, syncOrders } from '@/api/salesOrders'
import { useSyncStatus } from '@/composables/useSyncStatus'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const orders = ref([])
const total = ref(0)

const filter = reactive({
  keyword: '',
  state: '',
  dateRange: null,
  page: 1,
  page_size: 20,
})

const summaryQty = computed(() => {
  return orders.value.reduce((s, o) => s + (o.total_qty || 0), 0)
})

const summaryAmount = computed(() => {
  return orders.value.reduce((s, o) => s + (o.total_amount || 0), 0).toFixed(2)
})

function handleSearch() {
  filter.page = 1
  fetchOrders()
}

let _searchTimer = null
function debouncedSearch() {
  clearTimeout(_searchTimer)
  _searchTimer = setTimeout(() => handleSearch(), 350)
}

async function fetchOrders() {
  loading.value = true
  try {
    const params = {
      page: filter.page,
      page_size: filter.page_size,
    }
    if (filter.keyword) params.keyword = filter.keyword
    if (filter.state !== '' && filter.state !== null) params.state = filter.state
    if (filter.dateRange && filter.dateRange.length === 2) {
      params.date_start = filter.dateRange[0]
      params.date_end = filter.dateRange[1]
    }
    const res = await getSalesOrders(params)
    const d = res.data || {}
    orders.value = d.list || []
    total.value = d.total || 0
  } catch {
    orders.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

const { syncing } = useSyncStatus('orders', () => fetchOrders())

async function handleSync() {
  if (syncing.value) return
  syncing.value = true
  try {
    const res = await syncOrders(90)
    if (res.data?.already_syncing) {
      ElMessage.info('订单同步进行中，完成后将自动刷新')
    } else {
      ElMessage.success('同步已启动，完成后将自动刷新')
    }
  } catch {
    ElMessage.error('同步失败，请检查 ERP 配置')
    syncing.value = false
  }
}

function viewDetail(row) {
  router.push({ path: `/sales/${encodeURIComponent(row.order_no)}` })
}

function copyOrderNo(orderNo) {
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(orderNo).then(() => {
      ElMessage.success('单号已复制')
    }).catch(() => {
      fallbackCopy(orderNo)
    })
  } else {
    fallbackCopy(orderNo)
  }
}

function fallbackCopy(text) {
  const ta = document.createElement('textarea')
  ta.value = text
  ta.style.position = 'fixed'
  ta.style.left = '-9999px'
  document.body.appendChild(ta)
  ta.select()
  try {
    document.execCommand('copy')
    ElMessage.success('单号已复制')
  } catch {
    ElMessage.error('复制失败')
  }
  document.body.removeChild(ta)
}

onMounted(() => {
  if (route.query.customer) {
    filter.keyword = route.query.customer
  }
  fetchOrders()
})
</script>

<style scoped>
.lark-sales {
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
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  gap: 12px;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.lark-search-input-wrap {
  position: relative;
  display: flex;
  align-items: center;
}

.lark-search-input-wrap .search-icon {
  position: absolute;
  left: 10px;
  color: var(--lark-text-disabled);
  font-size: 14px;
  pointer-events: none;
}

.lark-input {
  height: 32px;
  padding: 0 12px 0 32px;
  border: 1px solid var(--lark-border-light);
  border-radius: var(--lark-radius);
  background: var(--lark-bg-base);
  font-size: 13px;
  color: var(--lark-text-primary);
  outline: none;
  width: 220px;
  transition: border-color 0.2s;
}

.lark-input:focus {
  border-color: var(--lark-primary);
}

.summary-bar {
  display: flex;
  align-items: center;
  gap: 24px;
  margin-bottom: 12px;
  padding: 8px 12px;
  background: var(--lark-bg-subtle, #f7f8fa);
  border-radius: var(--lark-radius);
  font-size: 13px;
  color: var(--lark-text-secondary);
}

.summary-item strong {
  color: var(--lark-text-primary);
  font-weight: 600;
}

.order-no {
  font-family: monospace;
  font-size: 13px;
  color: var(--lark-primary);
  font-weight: 500;
}

.amount {
  font-weight: 600;
  color: var(--lark-text-primary);
}

.lark-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

:deep(.el-table) {
  --el-table-border-color: var(--lark-border-light);
  --el-table-header-bg-color: var(--lark-bg-subtle);
  font-size: 14px;
}

.order-no.copyable {
  cursor: pointer;
  color: var(--el-color-primary, #409eff);
}

:deep(.el-table td.el-table__cell) {
  padding: 4px 0;
}

:deep(.el-table th.el-table__cell) {
  font-weight: 600;
  color: var(--lark-text-primary);
}

</style>
