<template>
  <div class="order-detail">
    <div class="detail-header">
      <el-button @click="goBack" :icon="ArrowLeft" class="back-btn">返回列表</el-button>
      <h2 class="detail-title">销售订单详情 - {{ order.order_no || '' }}</h2>
      <el-tag v-if="order.state != null" :type="order.state === 1 ? 'success' : 'warning'" size="default">
        {{ order.state === 1 ? '已审核' : '未审核' }}
      </el-tag>
      <div style="flex: 1"></div>
      <el-dropdown trigger="click" @command="handlePrintCommand">
        <el-button type="primary" :loading="printing">
          <el-icon style="margin-right: 4px"><Printer /></el-icon>
          打印 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="picking">打印拣货单</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <div class="detail-body" v-loading="loading">
      <!-- 基本信息 -->
      <div class="info-section">
        <h3 class="section-title">基本信息</h3>
        <el-descriptions :column="3" border size="small" class="info-desc">
          <el-descriptions-item label="单号">{{ order.order_no || '-' }}</el-descriptions-item>
          <el-descriptions-item label="订单日期">{{ order.order_date || '-' }}</el-descriptions-item>
          <el-descriptions-item label="印次">{{ order.print_count ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="客户名称">{{ order.customer_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="客户电话">{{ order.customer_tel || '-' }}</el-descriptions-item>
          <el-descriptions-item label="客户地址">{{ order.customer_addr || '-' }}</el-descriptions-item>
          <el-descriptions-item label="业务员">{{ order.salesperson || '-' }}</el-descriptions-item>
          <el-descriptions-item label="制单人">{{ order.creator || '-' }}</el-descriptions-item>
          <el-descriptions-item label="联系人">{{ order.contact_person || '-' }}</el-descriptions-item>
          <el-descriptions-item label="交货日期">{{ order.delivery_date || '-' }}</el-descriptions-item>
          <el-descriptions-item label="托运方式">{{ order.shipping_method || '-' }}</el-descriptions-item>
          <el-descriptions-item label="货运电话">{{ order.shipping_tel || '-' }}</el-descriptions-item>
          <el-descriptions-item label="货运地址" :span="3">{{ order.shipping_addr || '-' }}</el-descriptions-item>
          <el-descriptions-item label="客户类型">{{ order.customer_type || '-' }}</el-descriptions-item>
          <el-descriptions-item label="品牌">{{ order.brand || '-' }}</el-descriptions-item>
          <el-descriptions-item label="币种">{{ order.currency || '-' }}</el-descriptions-item>
          <el-descriptions-item label="总数量">
            <strong>{{ order.total_qty ?? 0 }}</strong>
          </el-descriptions-item>
          <el-descriptions-item label="总金额">
            <strong class="amount">¥{{ (order.total_amount ?? 0).toFixed?.(2) || '0.00' }}</strong>
          </el-descriptions-item>
          <el-descriptions-item label="付款金额">{{ order.payment_amount != null ? `¥${order.payment_amount}` : '-' }}</el-descriptions-item>
          <el-descriptions-item label="备注" :span="3">{{ order.remark || '-' }}</el-descriptions-item>
          <el-descriptions-item label="同步时间">{{ formatDateTime(order.synced_at) }}</el-descriptions-item>
        </el-descriptions>
      </div>

      <!-- 配货单打印记录 -->
      <div class="info-section" v-if="printHistory.length > 0">
        <h3 class="section-title">配货单打印记录</h3>
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

      <!-- 明细行 -->
      <div class="items-section">
        <h3 class="section-title">订单明细 <span class="item-count" v-if="items.length">（{{ items.length }} 项）</span></h3>
        <el-table :data="items" stripe size="default" class="items-table" show-summary :summary-method="summaryMethod" v-if="items.length">
          <el-table-column type="index" label="#" width="50" align="center" />
          <el-table-column label="品牌" prop="brand" width="100" />
          <el-table-column label="货号" prop="product_no" width="130" />
          <el-table-column label="品名" prop="product_name" width="120" show-overflow-tooltip />
          <el-table-column label="颜色" prop="color" width="100" />
          <el-table-column label="等级" prop="grade" width="80" />
          <el-table-column label="单位" prop="unit" width="60" align="center" />
          <el-table-column label="单价" width="90" align="right">
            <template #default="{ row }">
              {{ row.price > 0 ? row.price.toFixed(2) : '-' }}
            </template>
          </el-table-column>
          <el-table-column label="折扣" width="70" align="center">
            <template #default="{ row }">
              {{ row.discount < 100 ? row.discount + '%' : '-' }}
            </template>
          </el-table-column>
          <el-table-column label="尺码明细" min-width="280">
            <template #default="{ row }">
              <div class="size-tags">
                <el-tag
                  v-for="s in row.sizes"
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
        <el-empty v-else-if="!loading" description="无明细数据" :image-size="64" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Printer, ArrowDown } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { getOrderDetail, printPicking, getPickingPrintHistory } from '@/api/salesOrders'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const order = ref({})
const items = ref([])
const printing = ref(false)
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
  router.push('/sales')
}

async function fetchDetail() {
  const orderNo = route.params.orderNo
  if (!orderNo) return
  loading.value = true
  try {
    const res = await getOrderDetail(orderNo)
    if (res.code === 200 && res.data) {
      order.value = res.data.order || {}
      items.value = res.data.items || []
    }
  } catch (e) {
    console.error('获取订单详情失败:', e)
  } finally {
    loading.value = false
  }
}

function summaryMethod({ columns }) {
  const sums = []
  columns.forEach((col, index) => {
    if (index === 0) {
      sums[index] = '合计'
      return
    }
    if (col.property === 'total_qty') {
      sums[index] = items.value.reduce((s, item) => s + (item.total_qty || 0), 0)
      return
    }
    sums[index] = ''
  })
  return sums
}

async function handlePrintCommand(command) {
  if (command === 'picking') {
    await handlePrintPicking()
  }
}

async function handlePrintPicking() {
  const orderNo = order.value.order_no
  if (!orderNo) {
    ElMessage.warning('订单信息未加载')
    return
  }
  printing.value = true
  try {
    const res = await printPicking(orderNo)
    if (res.code === 200 && res.data?.oss_url) {
      window.open(res.data.oss_url, '_blank')
      ElMessage.success(`拣货单已生成（${res.data.page_count} 页${res.data.is_cached ? '，使用缓存' : ''}）`)
      await fetchPrintHistory()
    } else {
      ElMessage.error(res.message || '生成拣货单失败')
    }
  } catch (e) {
    console.error('打印拣货单失败:', e)
    ElMessage.error('打印拣货单失败，请重试')
  } finally {
    printing.value = false
  }
}

async function fetchPrintHistory() {
  const orderNo = route.params.orderNo
  if (!orderNo) return
  try {
    const res = await getPickingPrintHistory(orderNo)
    if (res.code === 200) {
      printHistory.value = res.data || []
    }
  } catch {}
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

.amount {
  color: #f56c6c;
}

:deep(.info-desc table) {
  table-layout: fixed;
}

:deep(.info-desc .el-descriptions__label) {
  width: 80px;
  font-weight: 500;
  padding: 8px 10px;
}

:deep(.info-desc .el-descriptions__content) {
  padding: 8px 10px;
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
