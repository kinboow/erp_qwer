<template>
  <div class="order-detail">
    <div class="detail-header">
      <el-button @click="goBack" :icon="ArrowLeft" class="back-btn">返回列表</el-button>
      <h2 class="detail-title">待发货详情 - {{ detail.order_no || '' }}</h2>
      <div style="flex:1"></div>
      <el-dropdown trigger="click" @command="handlePrintCommand">
        <el-button type="primary" :loading="printing">
          <el-icon style="margin-right: 4px"><Printer /></el-icon>
          打印本单 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="local">本地打印</el-dropdown-item>
            <el-dropdown-item command="remote">远程打印</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <div class="detail-body" v-loading="loading">
      <!-- 基本信息 -->
      <div class="info-section">
        <h3 class="section-title">基本信息</h3>
        <el-descriptions :column="3" border size="small" class="info-desc">
          <el-descriptions-item label="订单号">
            <router-link v-if="detail.order_no" :to="`/sales/${encodeURIComponent(detail.order_no)}`" class="link-text">{{ detail.order_no }}</router-link>
            <span v-else>-</span>
          </el-descriptions-item>
          <el-descriptions-item label="下单日期">{{ detail.order_date || '-' }}</el-descriptions-item>
          <el-descriptions-item label="客户名称">{{ customerName || detail.customer_id || '-' }}</el-descriptions-item>
          <el-descriptions-item label="货号">{{ detail.product_no || '-' }}</el-descriptions-item>
          <el-descriptions-item label="品名">{{ detail.product_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="颜色">{{ detail.color || '-' }}</el-descriptions-item>
          <el-descriptions-item label="品牌">{{ detail.brand || '-' }}</el-descriptions-item>
          <el-descriptions-item label="单位">{{ detail.unit || '-' }}</el-descriptions-item>
          <el-descriptions-item label="制单人">{{ detail.creator || '-' }}</el-descriptions-item>
          <el-descriptions-item label="客户类型">{{ detail.customer_type || '-' }}</el-descriptions-item>
          <el-descriptions-item label="客户订单号">{{ detail.customer_order_no || '-' }}</el-descriptions-item>
          <el-descriptions-item label="同步时间">{{ formatDateTime(detail.synced_at) }}</el-descriptions-item>
          <el-descriptions-item label="备注" :span="3">{{ detail.remark || '-' }}</el-descriptions-item>
        </el-descriptions>
      </div>

      <!-- 数量信息 -->
      <div class="info-section">
        <h3 class="section-title">数量信息</h3>
        <el-descriptions :column="4" border size="small" class="info-desc">
          <el-descriptions-item label="下单数">
            <strong>{{ detail.order_qty ?? 0 }}</strong>
          </el-descriptions-item>
          <el-descriptions-item label="已发货">{{ detail.shipped_qty ?? 0 }}</el-descriptions-item>
          <el-descriptions-item label="退货数">{{ detail.returned_qty ?? 0 }}</el-descriptions-item>
          <el-descriptions-item label="未发货数">
            <strong class="highlight">{{ detail.unshipped_qty ?? 0 }}</strong>
          </el-descriptions-item>
          <el-descriptions-item label="库存数">{{ detail.stock_qty ?? 0 }}</el-descriptions-item>
          <el-descriptions-item label="单价">{{ detail.price ? `¥${Number(detail.price).toFixed(2)}` : '-' }}</el-descriptions-item>
          <el-descriptions-item label="未发金额">
            <strong class="amount">{{ detail.unshipped_amount ? `¥${Number(detail.unshipped_amount).toFixed(2)}` : '-' }}</strong>
          </el-descriptions-item>
          <el-descriptions-item label="成本价">{{ detail.cost_price ? `¥${Number(detail.cost_price).toFixed(2)}` : '-' }}</el-descriptions-item>
        </el-descriptions>
      </div>

      <!-- 待发货单打印记录 -->
      <div class="info-section" v-if="printHistory.length > 0">
        <h3 class="section-title">待发货单打印记录</h3>
        <el-table :data="printHistory" size="small" stripe class="print-history-table">
          <el-table-column label="页码ID" width="180">
            <template #default="{ row }">
              <span :class="{ 'voided-id': row.status === 'voided' }">{{ row.page_id }}</span>
            </template>
          </el-table-column>
          <el-table-column label="页码" width="80" align="center">
            <template #default="{ row }">第 {{ row.page_index + 1 }} 页</template>
          </el-table-column>
          <el-table-column label="状态" width="100" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.status === 'active'" type="success" size="small">有效</el-tag>
              <el-tag v-else type="danger" size="small" effect="plain">已废除</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="生成时间" width="180">
            <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 未发尺码明细 -->
      <div class="items-section">
        <h3 class="section-title">未发尺码明细 <span class="item-count" v-if="detail.unshipped_sizes && detail.unshipped_sizes.length">（{{ detail.unshipped_sizes.length }} 项）</span></h3>
        <el-table :data="detail.unshipped_sizes || []" stripe size="default" class="items-table" show-summary :summary-method="sizeSummary" v-if="detail.unshipped_sizes && detail.unshipped_sizes.length">
          <el-table-column type="index" label="#" width="60" align="center" />
          <el-table-column label="尺码" prop="size" min-width="120" />
          <el-table-column label="数量" prop="qty" width="120" align="right" />
        </el-table>
        <el-empty v-else-if="!loading" description="无尺码明细" :image-size="64" />
      </div>

      <!-- 订单尺码明细 -->
      <div class="items-section" v-if="detail.order_sizes && detail.order_sizes.length">
        <h3 class="section-title">订单尺码明细 <span class="item-count">（{{ detail.order_sizes.length }} 项）</span></h3>
        <el-table :data="detail.order_sizes" stripe size="default" class="items-table" show-summary :summary-method="orderSizeSummary">
          <el-table-column type="index" label="#" width="60" align="center" />
          <el-table-column label="尺码" prop="size" min-width="120" />
          <el-table-column label="数量" prop="qty" width="120" align="right" />
        </el-table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, ArrowDown, Printer } from '@element-plus/icons-vue'
import { getUnshippedDetail, printUnshipped, getUnshippedPrintHistory } from '@/api/unshippedReport'
import { getCustomerList } from '@/api/customer'
import { ElMessage } from 'element-plus'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const printing = ref(false)
const detail = ref({})
const customerName = ref('')
const printHistory = ref([])

const formatDateTime = (val) => {
  if (!val) return '-'
  try {
    const d = new Date(val)
    if (isNaN(d.getTime())) return val
    const pad = (n) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  } catch {
    return val
  }
}

function goBack() {
  router.push('/unshipped-report')
}

function handlePrintCommand(command) {
  handlePrint(command)
}

async function handlePrint(mode = 'local') {
  const d = detail.value
  if (!d.id) return
  printing.value = true
  try {
    const res = await printUnshipped([d.id], customerName.value || '', mode)
    if (res.code === 200) {
      if (mode === 'remote' && res.data?.remote_queued) {
        ElMessage.success('待发货单已发送到远程打印机')
      } else if (res.data?.oss_url) {
        window.open(res.data.oss_url, '_blank')
        ElMessage.success('待发货单已生成')
      }
      await fetchPrintHistory()
    } else {
      ElMessage.error(res.message || '生成失败')
    }
  } catch (e) {
    console.error('打印失败:', e)
    ElMessage.error('打印失败，请重试')
  } finally {
    printing.value = false
  }
}

async function fetchPrintHistory() {
  const orderNo = detail.value?.order_no
  if (!orderNo) return
  try {
    const res = await getUnshippedPrintHistory(orderNo)
    if (res.code === 200) {
      printHistory.value = res.data || []
    }
  } catch {}
}

async function fetchDetail() {
  const id = route.params.id
  if (!id) return
  loading.value = true
  try {
    const res = await getUnshippedDetail(id)
    if (res.code === 200 && res.data) {
      detail.value = res.data
      if (res.data.customer_id) {
        fetchCustomerName(res.data.customer_id)
      }
    }
  } catch (e) {
    console.error('获取待发货详情失败:', e)
  } finally {
    loading.value = false
  }
}

async function fetchCustomerName(erpCustomerId) {
  try {
    const res = await getCustomerList({ page: 1, pageSize: 200 })
    const list = res.data?.list || []
    const found = list.find(c => c.erp_customer_id === erpCustomerId)
    if (found) customerName.value = found.customer_name
  } catch {}
}

function sizeSummary({ columns }) {
  const sums = []
  columns.forEach((col, index) => {
    if (index === 0) { sums[index] = '合计'; return }
    if (col.property === 'qty') {
      sums[index] = (detail.value.unshipped_sizes || []).reduce((s, item) => s + (item.qty || 0), 0)
      return
    }
    sums[index] = ''
  })
  return sums
}

function orderSizeSummary({ columns }) {
  const sums = []
  columns.forEach((col, index) => {
    if (index === 0) { sums[index] = '合计'; return }
    if (col.property === 'qty') {
      sums[index] = (detail.value.order_sizes || []).reduce((s, item) => s + (item.qty || 0), 0)
      return
    }
    sums[index] = ''
  })
  return sums
}

onMounted(async () => {
  await fetchDetail()
  await fetchPrintHistory()
})
</script>

<style scoped>
.order-detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: 100%;
  overflow: hidden;
}

.detail-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--lark-border-light, #e5e6eb);
  flex-shrink: 0;
}

.back-btn {
  flex-shrink: 0;
}

.detail-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--lark-text-primary, #1f2329);
  margin: 0;
}

.detail-body {
  display: flex;
  flex-direction: column;
  gap: 24px;
  flex: 1;
  overflow-y: auto;
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.detail-body::-webkit-scrollbar {
  display: none;
}

.info-section,
.items-section {
  background: var(--lark-bg-base, #fff);
  border-radius: var(--lark-radius-lg, 8px);
  padding: 20px 24px;
}

.section-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--lark-text-primary, #1f2329);
  margin: 0 0 12px;
}

.item-count {
  font-weight: 400;
  font-size: 13px;
  color: var(--lark-text-secondary, #646a73);
}

.highlight {
  color: #e6a23c;
}

.amount {
  color: #f56c6c;
}

.link-text {
  color: var(--el-color-primary, #409eff);
  text-decoration: none;
  font-weight: 500;
}

.link-text:hover {
  text-decoration: underline;
}

:deep(.info-desc table) {
  table-layout: fixed;
}

:deep(.info-desc .el-descriptions__label) {
  width: 90px;
  font-weight: 500;
  padding: 8px 10px;
}

:deep(.info-desc .el-descriptions__content) {
  padding: 8px 10px;
}

.items-table {
  font-size: 14px;
}

:deep(.items-table .el-table__body td.el-table__cell) {
  padding: 10px 0;
  font-size: 14px;
}

:deep(.items-table .el-table__footer td.el-table__cell) {
  padding: 6px 0;
  font-weight: 600;
  font-size: 13px;
}

.voided-id {
  text-decoration: line-through;
  color: #999;
}

.print-history-table {
  font-size: 13px;
}
</style>
