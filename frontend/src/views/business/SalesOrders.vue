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
              @keyup.enter="handleSearch"
            />
          </div>
        </div>
        <div class="toolbar-right">
          <el-button :icon="Refresh" @click="handleSearch" :loading="loading">刷新</el-button>
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
        @expand-change="handleExpand"
      >
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="expand-detail" v-loading="row._loadingItems">
              <el-table
                v-if="row._items && row._items.length"
                :data="row._items"
                size="small"
                class="detail-table"
                :show-header="true"
              >
                <el-table-column label="#" prop="sort_index" width="50" align="center" />
                <el-table-column label="货号" prop="product_no" width="120" />
                <el-table-column label="颜色" prop="color" width="100" />
                <el-table-column label="单位" prop="unit" width="60" align="center" />
                <el-table-column label="单价" width="90" align="right">
                  <template #default="{ row: item }">
                    {{ item.price > 0 ? item.price.toFixed(2) : '-' }}
                  </template>
                </el-table-column>
                <el-table-column label="尺码明细" min-width="260">
                  <template #default="{ row: item }">
                    <div class="size-tags">
                      <el-tag
                        v-for="s in item.sizes"
                        :key="s.size"
                        size="small"
                        type="info"
                        class="size-tag"
                      >
                        {{ s.size }}: {{ s.qty }}
                      </el-tag>
                    </div>
                  </template>
                </el-table-column>
                <el-table-column label="小计" prop="total_qty" width="80" align="right" />
                <el-table-column label="备注" prop="remark" min-width="120" show-overflow-tooltip />
              </el-table>
              <el-empty v-else-if="!row._loadingItems" description="无明细数据" :image-size="48" />
            </div>
          </template>
        </el-table-column>

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
            <span class="order-no">{{ row.order_no }}</span>
          </template>
        </el-table-column>
        <el-table-column label="订单日期" prop="order_date" width="110" />
        <el-table-column label="客户名称" prop="customer_name" min-width="140" show-overflow-tooltip />
        <el-table-column label="客户电话" prop="customer_tel" width="130" show-overflow-tooltip />
        <el-table-column label="客户地址" prop="customer_addr" min-width="160" show-overflow-tooltip />
        <el-table-column label="货号" prop="product_no" width="130" show-overflow-tooltip />
        <el-table-column label="总数量" prop="total_qty" width="80" align="right" />
        <el-table-column label="业务员" prop="salesperson" width="90" />
        <el-table-column label="托运方式" prop="shipping_method" width="100" />
        <el-table-column label="运费" width="90" align="right">
          <template #default="{ row }">
            {{ row.total_amount > 0 ? '-' : '-' }}
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
import { useRoute } from 'vue-router'
import { Search, Refresh } from '@element-plus/icons-vue'
import { getSalesOrders, getOrderItems } from '@/api/salesOrders'

const route = useRoute()
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
    orders.value = (d.list || []).map(o => ({ ...o, _items: null, _loadingItems: false }))
    total.value = d.total || 0
  } catch {
    orders.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

async function handleExpand(row, expandedRows) {
  if (!expandedRows.includes(row)) return
  if (row._items !== null) return
  row._loadingItems = true
  try {
    const res = await getOrderItems(row.order_no)
    row._items = res.data || []
  } catch {
    row._items = []
  } finally {
    row._loadingItems = false
  }
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

.expand-detail {
  padding: 12px 16px 12px 48px;
}

.detail-table {
  font-size: 12px;
}

.size-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.size-tag {
  font-size: 11px;
  border-radius: 4px;
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

:deep(.el-table th.el-table__cell) {
  font-weight: 600;
  color: var(--lark-text-primary);
}

:deep(.el-table__expanded-cell) {
  padding: 0 !important;
  background: var(--lark-bg-subtle, #fafbfc);
}
</style>
