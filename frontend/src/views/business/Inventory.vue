<template>
  <div class="lark-inventory">
    <div class="lark-page-header">
      <h2 class="header-title">库存查询</h2>
      <p class="header-desc">查询 ERP 系统中的实时库存信息</p>
    </div>

    <div class="lark-table-panel">
      <!-- 工具栏 -->
      <div class="lark-toolbar">
        <div class="toolbar-left">
          <el-input
            v-model="filter.product_no"
            placeholder="货号"
            clearable
            :prefix-icon="Search"
            style="width: 160px"
            @input="debouncedSearch"
            @clear="debouncedSearch"
          />
          <el-input
            v-model="filter.product_name"
            placeholder="品名"
            clearable
            style="width: 160px"
            @input="debouncedSearch"
            @clear="debouncedSearch"
          />
          <el-input
            v-model="filter.warehouse"
            placeholder="仓库"
            clearable
            style="width: 140px"
            @input="debouncedSearch"
            @clear="debouncedSearch"
          />
          <el-input
            v-model="filter.product_type"
            placeholder="产品类型"
            clearable
            style="width: 140px"
            @input="debouncedSearch"
            @clear="debouncedSearch"
          />
          <el-checkbox v-model="filter.show_zero" @change="handleSearch">显示零库存</el-checkbox>
          <el-checkbox v-model="filter.show_negative" @change="handleSearch">显示负库存</el-checkbox>
        </div>
        <div class="toolbar-right">
          <el-button :icon="syncing ? undefined : Refresh" @click="handleSync" :loading="syncing">{{ syncing ? `同步库存中${trigger === 'scheduled' ? '（定时）' : ''}...` : '同步库存' }}</el-button>
        </div>
      </div>

      <!-- 统计 -->
      <div class="summary-bar" v-if="total > 0">
        <span class="summary-item">共 <strong>{{ total }}</strong> 条记录</span>
        <span class="summary-item">总库存数量 <strong>{{ totalQty }}</strong></span>
        <span class="summary-item">总金额 <strong>¥{{ totalAmount }}</strong></span>
      </div>

      <!-- 表格 — 按货号分组 -->
      <el-table
        :data="rows"
        v-loading="loading"
        stripe
        class="lark-table"
        :default-sort="{ prop: 'product_no', order: 'ascending' }"
        style="flex: 1"
      >
        <el-table-column type="index" label="#" width="50" align="center" />
        <el-table-column label="图片" width="70" align="center">
          <template #default="{ row }">
            <el-image
              v-if="row.image_url"
              :src="row.image_url"
              :preview-src-list="[row.image_url]"
              fit="contain"
              style="width: 40px; height: 40px;"
              lazy
            />
            <span v-else class="no-img">-</span>
          </template>
        </el-table-column>
        <el-table-column label="货号" prop="product_no" width="150" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="product-no" @click.stop="copyText(row.product_no)" title="点击复制">{{ row.product_no || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="品名" prop="product_name" min-width="160" show-overflow-tooltip />
        <el-table-column label="类型" prop="product_type" width="100" show-overflow-tooltip />
        <el-table-column label="材质" prop="material" width="100" show-overflow-tooltip />
        <el-table-column label="单位" prop="unit" width="60" align="center" />
        <el-table-column label="颜色数" prop="color_count" width="80" align="center" />
        <el-table-column label="总库存" prop="total_qty" width="100" align="right" sortable>
          <template #default="{ row }">
            <span :class="{ 'qty-negative': row.total_qty < 0, 'qty-zero': row.total_qty === 0 }">
              {{ Math.round(row.total_qty ?? 0) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="总金额" prop="total_amount" width="110" align="right">
          <template #default="{ row }">
            <span class="amount-text">{{ row.total_amount > 0 ? Number(row.total_amount).toFixed(2) : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" align="center" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="viewDetail(row)">查看详情</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 详情弹窗 -->
      <el-dialog v-model="detailVisible" :title="`库存详情 — ${detailRow.product_no || ''}`" width="900px" destroy-on-close>
        <div class="detail-header">
          <span><strong>货号：</strong>{{ detailRow.product_no }}</span>
          <span><strong>品名：</strong>{{ detailRow.product_name }}</span>
          <span><strong>总库存：</strong>{{ Math.round(detailRow.total_qty || 0) }}</span>
          <span><strong>总金额：</strong>¥{{ Number(detailRow.total_amount || 0).toFixed(2) }}</span>
        </div>
        <el-table :data="detailRow.colors || []" stripe class="lark-table" style="margin-top: 12px">
          <el-table-column label="仓库" prop="warehouse" width="120" show-overflow-tooltip />
          <el-table-column label="颜色" prop="color" width="120" show-overflow-tooltip />
          <el-table-column label="库存数量" prop="qty" width="100" align="right">
            <template #default="{ row }">
              <span :class="{ 'qty-negative': row.qty < 0, 'qty-zero': row.qty === 0 }">{{ Math.round(row.qty || 0) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="尺码明细" min-width="200">
            <template #default="{ row }">
              <div v-if="row.sizes && row.sizes.length > 0" class="size-tags">
                <el-tag v-for="s in row.sizes" :key="s.size" size="small" effect="plain" class="size-tag">
                  {{ s.size }}: {{ s.qty }}
                </el-tag>
              </div>
              <span v-else>-</span>
            </template>
          </el-table-column>
        </el-table>
      </el-dialog>

      <!-- 分页 -->
      <div class="lark-pagination" v-if="total > 0">
        <el-pagination
          v-model:current-page="filter.page"
          v-model:page-size="filter.rows"
          :page-sizes="[50, 100, 200, 500]"
          :total="total"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="fetchInventory"
          @current-change="fetchInventory"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Search, Refresh } from '@element-plus/icons-vue'
import request from '@/utils/request'
import { useSyncStatus } from '@/composables/useSyncStatus'

const route = useRoute()

const loading = ref(false)
const rows = ref([])
const total = ref(0)
const detailVisible = ref(false)
const detailRow = ref({})

const filter = reactive({
  warehouse: '',
  product_type: '',
  product_no: '',
  product_no_exact: '',
  product_name: '',
  show_zero: false,
  show_negative: false,
  page: 1,
  rows: 200,
})

const totalQty = computed(() => {
  return rows.value.reduce((sum, r) => sum + (Number(r.total_qty) || 0), 0)
})

const totalAmount = computed(() => {
  return rows.value.reduce((sum, r) => sum + (Number(r.total_amount) || 0), 0).toFixed(2)
})

function handleSearch() {
  filter.page = 1
  filter.product_no_exact = ''
  fetchInventory()
}

let _searchTimer = null
function debouncedSearch() {
  clearTimeout(_searchTimer)
  _searchTimer = setTimeout(() => handleSearch(), 350)
}

async function fetchInventory() {
  loading.value = true
  try {
    const params = {
      page: filter.page,
      page_size: filter.rows,
      show_zero: filter.show_zero,
      show_negative: filter.show_negative,
    }
    if (filter.warehouse) params.warehouse = filter.warehouse
    if (filter.product_type) params.product_type = filter.product_type
    if (filter.product_no_exact) params.product_no_exact = filter.product_no_exact
    else if (filter.product_no) params.product_no = filter.product_no
    if (filter.product_name) params.product_name = filter.product_name

    const res = await request({ url: '/api/inventory/grouped', method: 'get', params })
    const d = res.data || {}
    rows.value = d.list || []
    total.value = d.total || 0
  } catch (e) {
    console.error('获取库存失败:', e)
    rows.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

const { syncing, trigger } = useSyncStatus('inventory', fetchInventory)

function viewDetail(row) {
  detailRow.value = row
  detailVisible.value = true
}

async function handleSync() {
  if (syncing.value) return
  syncing.value = true
  try {
    const res = await request({ url: '/api/erp/sync/trigger-inventory', method: 'post' })
    if (res.data?.already_syncing) {
      ElMessage.info('库存同步进行中，完成后将自动刷新')
    } else {
      ElMessage.success('同步已启动，完成后将自动刷新')
    }
  } catch {
    ElMessage.error('库存同步失败，请检查 ERP 配置')
    syncing.value = false
  }
}

function copyText(text) {
  if (!text) return
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(() => {
      ElMessage.success('已复制')
    }).catch(() => fallbackCopy(text))
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
  try {
    document.execCommand('copy')
    ElMessage.success('已复制')
  } catch {
    ElMessage.error('复制失败')
  }
  document.body.removeChild(ta)
}

onMounted(() => {
  if (route.query.product_no_exact) {
    filter.product_no = String(route.query.product_no_exact)
    filter.product_no_exact = String(route.query.product_no_exact)
  } else if (route.query.product_no) {
    filter.product_no = String(route.query.product_no)
  }
  if (route.query.warehouse) {
    filter.warehouse = String(route.query.warehouse)
  }
  fetchInventory()
})
</script>

<style scoped>
.lark-inventory {
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

.product-no {
  cursor: pointer;
  color: var(--el-color-primary, #409eff);
  font-weight: 500;
}

.no-img {
  color: var(--lark-text-disabled);
}

.qty-negative {
  color: #f56c6c;
  font-weight: 600;
}

.qty-zero {
  color: var(--lark-text-disabled);
}

.amount-text {
  font-weight: 500;
}

.size-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.size-tag {
  font-size: 12px;
}

.detail-header {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
  font-size: 14px;
  color: var(--lark-text-secondary);
  padding: 8px 0;
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

:deep(.el-table td.el-table__cell) {
  padding: 6px 0;
}

:deep(.el-table th.el-table__cell) {
  font-weight: 600;
  color: var(--lark-text-primary);
}
</style>
