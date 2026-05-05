<template>
  <div class="scan-records-page">
    <!-- 统计卡片 -->
    <div class="stats-bar">
      <div class="stat-card">
        <div class="stat-value">{{ stats.total || 0 }}</div>
        <div class="stat-label">总计</div>
      </div>
      <div class="stat-card stat-success">
        <div class="stat-value">{{ stats.success_count || 0 }}</div>
        <div class="stat-label">成功</div>
      </div>
      <div class="stat-card stat-fail">
        <div class="stat-value">{{ stats.failed_count || 0 }}</div>
        <div class="stat-label">失败</div>
      </div>
      <div class="stat-card stat-pending">
        <div class="stat-value">{{ stats.pending_count || 0 }}</div>
        <div class="stat-label">处理中</div>
      </div>
    </div>

    <!-- 筛选栏 -->
    <div class="filter-bar">
      <el-input v-model="filters.order_no" placeholder="搜索订单号" clearable style="width:200px" @keyup.enter="fetchData" />
      <el-select v-model="filters.scan_status" placeholder="识别状态" clearable style="width:140px" @change="fetchData">
        <el-option label="成功" value="success" />
        <el-option label="失败" value="failed" />
        <el-option label="处理中" value="pending" />
      </el-select>
      <el-button type="primary" @click="fetchData">查询</el-button>
      <el-button @click="resetFilters">重置</el-button>
    </div>

    <!-- 数据表格 -->
    <el-table :data="tableData" v-loading="loading" border stripe style="width:100%" @row-click="onRowClick">
      <el-table-column label="图片" width="90" align="center">
        <template #default="{ row }">
          <div class="thumb-wrap" v-if="row.msg_log_id && row.image_oss_key" @click.stop="previewImage(row)">
            <img :src="mediaUrl(row.msg_log_id)" class="thumb-img" loading="lazy" />
          </div>
          <span v-else style="color:#c0c4cc;font-size:12px">无图</span>
        </template>
      </el-table-column>
      <el-table-column label="订单号" prop="order_no" min-width="130">
        <template #default="{ row }">
          <span v-if="row.order_no" class="link-text" @click.stop="goToOrder(row.order_no)">{{ row.order_no }}</span>
          <span v-else style="color:#c0c4cc">-</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.scan_status)" size="small">{{ statusText(row.scan_status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="发货单号" prop="shipment_no" min-width="130">
        <template #default="{ row }">
          <span v-if="row.shipment_no">{{ row.shipment_no }}</span>
          <span v-else style="color:#c0c4cc">-</span>
        </template>
      </el-table-column>
      <el-table-column label="纸张ID" prop="paper_id" min-width="120" show-overflow-tooltip />
      <el-table-column label="扫码人" prop="scanner_name" width="100">
        <template #default="{ row }">
          {{ row.scanner_name || row.sender_id || '-' }}
        </template>
      </el-table-column>
      <el-table-column label="群名" prop="room_name" min-width="120" show-overflow-tooltip />
      <el-table-column label="错误信息" prop="error_message" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">
          <span v-if="row.error_message" style="color:#f56c6c">{{ row.error_message }}</span>
          <span v-else style="color:#c0c4cc">-</span>
        </template>
      </el-table-column>
      <el-table-column label="时间" width="160" align="center">
        <template #default="{ row }">
          {{ formatDate(row.created_at) }}
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <div class="pagination-bar">
      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.pageSize"
        :total="pagination.total"
        :page-sizes="[20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        @current-change="fetchData"
        @size-change="fetchData"
      />
    </div>

    <!-- 图片预览 -->
    <el-image-viewer
      v-if="previewUrl"
      :url-list="[previewUrl]"
      :initial-index="0"
      @close="previewUrl = ''"
      teleported
    />

    <!-- 详情抽屉 -->
    <el-drawer v-model="drawerVisible" title="识别详情" size="520px" direction="rtl">
      <template v-if="selectedRecord">
        <div class="detail-section">
          <div class="detail-row">
            <span class="detail-label">订单号</span>
            <span class="detail-value link-text" v-if="selectedRecord.order_no" @click="goToOrder(selectedRecord.order_no)">{{ selectedRecord.order_no }}</span>
            <span class="detail-value" v-else>-</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">状态</span>
            <el-tag :type="statusTagType(selectedRecord.scan_status)" size="small">{{ statusText(selectedRecord.scan_status) }}</el-tag>
          </div>
          <div class="detail-row">
            <span class="detail-label">发货单号</span>
            <span class="detail-value">{{ selectedRecord.shipment_no || '-' }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">纸张ID</span>
            <span class="detail-value" style="word-break:break-all">{{ selectedRecord.paper_id || '-' }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">扫码人</span>
            <span class="detail-value">{{ selectedRecord.scanner_name || selectedRecord.sender_id || '-' }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">群名</span>
            <span class="detail-value">{{ selectedRecord.room_name || '-' }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">时间</span>
            <span class="detail-value">{{ formatDate(selectedRecord.created_at) }}</span>
          </div>
          <div class="detail-row" v-if="selectedRecord.error_message">
            <span class="detail-label">错误信息</span>
            <span class="detail-value" style="color:#f56c6c">{{ selectedRecord.error_message }}</span>
          </div>
        </div>

        <el-divider>扫码图片</el-divider>
        <div class="detail-image" v-if="selectedRecord.msg_log_id && selectedRecord.image_oss_key">
          <img :src="mediaUrl(selectedRecord.msg_log_id)" class="detail-img" @click="previewImage(selectedRecord)" />
        </div>
        <div v-else style="color:#c0c4cc;text-align:center;padding:20px">无图片</div>

        <el-divider v-if="selectedRecord.ai_parsed">AI 识别结果</el-divider>
        <div v-if="selectedRecord.ai_parsed" class="ai-result-block">
          <pre class="ai-json">{{ JSON.stringify(selectedRecord.ai_parsed, null, 2) }}</pre>
        </div>

        <el-divider v-if="selectedRecord.qr_content">二维码内容</el-divider>
        <div v-if="selectedRecord.qr_content" class="qr-content-block">
          <code>{{ selectedRecord.qr_content }}</code>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElImageViewer } from 'element-plus'
import { getScanRecords, getScanStats } from '@/api/shippingScans'

const router = useRouter()
const loading = ref(false)
const tableData = ref([])
const stats = ref({})
const previewUrl = ref('')
const drawerVisible = ref(false)
const selectedRecord = ref(null)

const filters = reactive({
  order_no: '',
  scan_status: ''
})

const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
})

const mediaUrl = (msgLogId) => {
  const t = localStorage.getItem('token') || ''
  return `/api/downstream-orders/media/${msgLogId}?token=${encodeURIComponent(t)}`
}

const fetchData = async () => {
  loading.value = true
  try {
    const res = await getScanRecords({
      page: pagination.page,
      pageSize: pagination.pageSize,
      scan_status: filters.scan_status || undefined,
      order_no: filters.order_no || undefined
    })
    const d = res.data || {}
    tableData.value = d.list || []
    pagination.total = d.total || 0
  } finally {
    loading.value = false
  }
}

const fetchStats = async () => {
  try {
    const res = await getScanStats()
    stats.value = res.data || {}
  } catch (e) { /* ignore */ }
}

const resetFilters = () => {
  filters.order_no = ''
  filters.scan_status = ''
  pagination.page = 1
  fetchData()
}

const statusText = (s) => {
  const map = { success: '成功', failed: '失败', pending: '处理中' }
  return map[s] || s || '-'
}

const statusTagType = (s) => {
  const map = { success: 'success', failed: 'danger', pending: 'warning' }
  return map[s] || 'info'
}

const formatDate = (v) => {
  if (!v) return '-'
  return String(v).replace('T', ' ').slice(0, 19)
}

const previewImage = (row) => {
  if (row.msg_log_id && row.image_oss_key) {
    previewUrl.value = mediaUrl(row.msg_log_id)
  }
}

const onRowClick = (row) => {
  selectedRecord.value = row
  drawerVisible.value = true
}

const goToOrder = (orderNo) => {
  if (orderNo) router.push(`/sales/${encodeURIComponent(orderNo)}`)
}

onMounted(() => {
  fetchData()
  fetchStats()
})
</script>

<style scoped>
.scan-records-page {
  padding: 20px;
  background: #f5f6f8;
  min-height: 100%;
}

.stats-bar {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
}
.stat-card {
  flex: 1;
  background: #fff;
  border-radius: 8px;
  padding: 16px 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,.06);
}
.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: #303133;
}
.stat-label {
  font-size: 13px;
  color: #909399;
  margin-top: 4px;
}
.stat-success .stat-value { color: #67c23a; }
.stat-fail .stat-value { color: #f56c6c; }
.stat-pending .stat-value { color: #e6a23c; }

.filter-bar {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
  align-items: center;
}

.thumb-wrap {
  width: 60px;
  height: 60px;
  overflow: hidden;
  border-radius: 4px;
  cursor: pointer;
  border: 1px solid #ebeef5;
  display: flex;
  align-items: center;
  justify-content: center;
}
.thumb-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.thumb-wrap:hover {
  border-color: #409eff;
}

.link-text {
  color: #409eff;
  cursor: pointer;
}
.link-text:hover {
  text-decoration: underline;
}

.pagination-bar {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

/* 详情抽屉 */
.detail-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.detail-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}
.detail-label {
  min-width: 72px;
  font-weight: 600;
  color: #606266;
  flex-shrink: 0;
}
.detail-value {
  color: #303133;
  word-break: break-all;
}

.detail-image {
  text-align: center;
}
.detail-img {
  max-width: 100%;
  max-height: 400px;
  border-radius: 6px;
  cursor: pointer;
  border: 1px solid #ebeef5;
}
.detail-img:hover {
  border-color: #409eff;
}

.ai-result-block {
  background: #fafafa;
  border-radius: 6px;
  padding: 12px;
  overflow: auto;
  max-height: 300px;
}
.ai-json {
  font-size: 12px;
  font-family: 'Consolas', 'Monaco', monospace;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
  color: #303133;
}

.qr-content-block {
  background: #fafafa;
  border-radius: 6px;
  padding: 12px;
  word-break: break-all;
}
.qr-content-block code {
  font-size: 12px;
  color: #606266;
}
</style>
