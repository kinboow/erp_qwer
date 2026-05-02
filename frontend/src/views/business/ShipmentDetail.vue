<template>
  <div class="order-detail">
    <div class="detail-header">
      <el-button @click="goBack" :icon="ArrowLeft" class="back-btn">返回列表</el-button>
      <h2 class="detail-title">销售发货单详情 - {{ shipment.order_no || '' }}</h2>
      <el-tag v-if="shipment.state != null" :type="shipment.state === 1 ? 'success' : 'warning'" size="default">
        {{ shipment.state === 1 ? '已审核' : '未审核' }}
      </el-tag>
    </div>

    <div class="detail-body" v-loading="loading">
      <!-- 基本信息 -->
      <div class="info-section">
        <h3 class="section-title">基本信息</h3>
        <el-descriptions :column="3" border size="small" class="info-desc">
          <el-descriptions-item label="发货单号">{{ shipment.order_no || '-' }}</el-descriptions-item>
          <el-descriptions-item label="发货日期">{{ shipment.order_date || '-' }}</el-descriptions-item>
          <el-descriptions-item label="仓库">{{ shipment.warehouse || '-' }}</el-descriptions-item>
          <el-descriptions-item label="客户名称">{{ shipment.customer_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="客户电话">{{ shipment.customer_tel || '-' }}</el-descriptions-item>
          <el-descriptions-item label="客户地址">{{ shipment.customer_addr || '-' }}</el-descriptions-item>
          <el-descriptions-item label="业务员">{{ shipment.salesperson || '-' }}</el-descriptions-item>
          <el-descriptions-item label="制单人">{{ shipment.creator || '-' }}</el-descriptions-item>
          <el-descriptions-item label="经手人">{{ shipment.handler || '-' }}</el-descriptions-item>
          <el-descriptions-item label="联系人">{{ shipment.contact_person || '-' }}</el-descriptions-item>
          <el-descriptions-item label="联系电话">{{ shipment.contact_tel || '-' }}</el-descriptions-item>
          <el-descriptions-item label="配送人员">{{ shipment.delivery_person || '-' }}</el-descriptions-item>
          <el-descriptions-item label="配送方式">{{ shipment.shipping_method || '-' }}</el-descriptions-item>
          <el-descriptions-item label="货运电话">{{ shipment.shipping_tel || '-' }}</el-descriptions-item>
          <el-descriptions-item label="快递单号">{{ shipment.tracking_no || '-' }}</el-descriptions-item>
          <el-descriptions-item label="货运地址" :span="3">{{ shipment.shipping_addr || '-' }}</el-descriptions-item>
          <el-descriptions-item label="客户类型">{{ shipment.customer_type || '-' }}</el-descriptions-item>
          <el-descriptions-item label="币种">{{ shipment.currency || '-' }}</el-descriptions-item>
          <el-descriptions-item label="运费">
            {{ shipment.freight != null ? `¥${Number(shipment.freight).toFixed(2)}` : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="总数量">
            <strong>{{ shipment.total_qty ?? 0 }}</strong>
          </el-descriptions-item>
          <el-descriptions-item label="总金额">
            <strong class="amount">¥{{ (shipment.total_amount ?? 0).toFixed?.(2) || '0.00' }}</strong>
          </el-descriptions-item>
          <el-descriptions-item label="付款金额">{{ shipment.payment_amount != null ? `¥${shipment.payment_amount}` : '-' }}</el-descriptions-item>
          <el-descriptions-item label="备注" :span="3">{{ shipment.remark || '-' }}</el-descriptions-item>
          <el-descriptions-item label="同步时间">{{ formatDateTime(shipment.synced_at) }}</el-descriptions-item>
        </el-descriptions>
      </div>

      <!-- 明细行 -->
      <div class="items-section">
        <h3 class="section-title">发货明细 <span class="item-count" v-if="items.length">（{{ items.length }} 项）</span></h3>
        <el-table :data="items" stripe size="default" class="items-table" show-summary :summary-method="summaryMethod" v-if="items.length">
          <el-table-column type="index" label="#" width="50" align="center" />
          <el-table-column label="品牌" prop="brand" width="100" />
          <el-table-column label="货号" prop="product_no" width="130" />
          <el-table-column label="品名" prop="product_name" width="120" show-overflow-tooltip />
          <el-table-column label="颜色" prop="color" width="100" />
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
          <el-table-column label="关联订单" width="200">
            <template #default="{ row }">
              <span v-if="row.order_ref" class="order-ref-cell">
                <el-tooltip :content="row.order_ref" placement="top" :show-after="300">
                  <span class="order-ref-link" @click="goToOrder(row.order_ref)">{{ row.order_ref }}</span>
                </el-tooltip>
                <el-button link type="primary" size="small" class="copy-btn" @click="copyText(row.order_ref)">复制</el-button>
              </span>
              <span v-else>-</span>
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
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft } from '@element-plus/icons-vue'
import { getShipmentDetail, getShipmentItems } from '@/api/salesShipments'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const shipment = ref({})
const items = ref([])

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
  router.push('/shipments')
}

async function fetchDetail() {
  const orderNo = route.params.orderNo
  if (!orderNo) return
  loading.value = true
  try {
    const [detailRes, itemsRes] = await Promise.all([
      getShipmentDetail(orderNo),
      getShipmentItems(orderNo),
    ])
    if (detailRes.code === 200 && detailRes.data) {
      shipment.value = detailRes.data
    }
    if (itemsRes.code === 200 && itemsRes.data) {
      items.value = itemsRes.data
    }
  } catch (e) {
    console.error('获取发货单详情失败:', e)
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

function goToOrder(orderNo) {
  if (orderNo) {
    router.push({ path: `/sales/${encodeURIComponent(orderNo)}` })
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

onMounted(fetchDetail)
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

.order-ref-cell {
  display: flex;
  align-items: center;
  gap: 4px;
  max-width: 100%;
}

.order-ref-link {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
  flex: 1;
  color: var(--el-color-primary, #409eff);
  cursor: pointer;
}

.order-ref-link:hover {
  text-decoration: underline;
}

.copy-btn {
  flex-shrink: 0;
  padding: 0 2px;
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
</style>
