<template>
  <div class="lark-products">
    <div class="lark-page-header">
      <h2 class="header-title">产品列表</h2>
      <p class="header-desc">查看 ERP 系统中的产品信息</p>
    </div>

    <div class="lark-table-panel">
      <!-- 工具栏 -->
      <div class="lark-toolbar">
        <div class="toolbar-left">
          <el-input
            v-model="filter.keyword"
            placeholder="搜索货号/品名"
            clearable
            :prefix-icon="Search"
            style="width: 220px"
            @keyup.enter="handleSearch"
            @clear="handleSearch"
          />
          <el-button type="primary" :icon="Search" @click="handleSearch">搜索</el-button>
        </div>
        <div class="toolbar-right">
          <el-button :icon="Refresh" @click="handleSync" :loading="syncing">同步产品列表</el-button>
        </div>
      </div>

      <!-- 统计 -->
      <div class="summary-bar" v-if="total > 0">
        <span class="summary-item">共 <strong>{{ total }}</strong> 个产品</span>
      </div>

      <!-- 表格 -->
      <el-table
        :data="allProducts"
        v-loading="loading"
        stripe
        class="lark-table"
      >
        <el-table-column type="index" label="序号" width="60" align="center" />
        <el-table-column label="货号" prop="product_no" width="150" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="product-no" @click.stop="copyText(row.product_no)" title="点击复制">{{ row.product_no || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="品名" prop="product_name" min-width="160" show-overflow-tooltip />
        <el-table-column label="颜色" prop="color" min-width="140" show-overflow-tooltip />
        <el-table-column label="单位" prop="unit" width="70" align="center" />
        <el-table-column label="单价" width="90" align="right">
          <template #default="{ row }">
            {{ row.price != null && row.price > 0 ? Number(row.price).toFixed(2) : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="尺码" prop="spec" min-width="120" show-overflow-tooltip />
        <el-table-column label="备注" prop="remark" min-width="120" show-overflow-tooltip />
        <el-table-column label="操作" width="180" fixed="right" align="center">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="viewDetail(row)">查看详情</el-button>
            <el-button type="primary" link size="small" @click="viewInventory(row)">查看库存</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="lark-pagination" v-if="total > 0">
        <el-pagination
          v-model:current-page="filter.page"
          v-model:page-size="filter.page_size"
          :page-sizes="[20, 50, 100, 200]"
          :total="total"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="fetchProducts"
          @current-change="fetchProducts"
        />
      </div>
    </div>

    <!-- 产品详情弹窗 -->
    <el-dialog v-model="detailVisible" title="产品详情" width="640px" destroy-on-close>
      <el-descriptions :column="2" border size="default" class="product-detail-desc">
        <el-descriptions-item label="货号">{{ detailData.product_no || '-' }}</el-descriptions-item>
        <el-descriptions-item label="品名">{{ detailData.product_name || '-' }}</el-descriptions-item>
        <el-descriptions-item label="品牌">{{ detailData.brand || '-' }}</el-descriptions-item>
        <el-descriptions-item label="类别">{{ detailData.category || '-' }}</el-descriptions-item>
        <el-descriptions-item label="材质">{{ detailData.material || '-' }}</el-descriptions-item>
        <el-descriptions-item label="单位">{{ detailData.unit || '-' }}</el-descriptions-item>
        <el-descriptions-item label="单价">
          <span class="price-text">{{ detailData.price > 0 ? `¥${Number(detailData.price).toFixed(2)}` : '-' }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="产品编号">{{ detailData.product_id || '-' }}</el-descriptions-item>
        <el-descriptions-item label="颜色" :span="2">{{ detailData.color || '-' }}</el-descriptions-item>
        <el-descriptions-item label="尺码" :span="2">{{ detailData.spec || '-' }}</el-descriptions-item>
        <el-descriptions-item label="图片" :span="2">
          <el-image
            v-if="detailData.image_url"
            :src="detailData.image_url"
            :preview-src-list="[detailData.image_url]"
            fit="contain"
            style="width: 120px; height: 120px;"
          />
          <span v-else>-</span>
        </el-descriptions-item>
        <el-descriptions-item label="备注" :span="2">{{ detailData.remark || '-' }}</el-descriptions-item>
        <el-descriptions-item label="同步时间" :span="2">{{ detailData.synced_at || '-' }}</el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Search, Refresh } from '@element-plus/icons-vue'
import { getProducts, syncProducts } from '@/api/products'

const loading = ref(false)
const syncing = ref(false)
const allProducts = ref([])
const total = ref(0)
const detailVisible = ref(false)
const detailData = ref({})

const filter = reactive({
  keyword: '',
  page: 1,
  page_size: 50,
})


function handleSearch() {
  filter.page = 1
  fetchProducts()
}

async function handleSync() {
  syncing.value = true
  try {
    const res = await syncProducts()
    const d = res.data || {}
    ElMessage.success(`同步完成：共 ${d.total_found || 0} 个，成功 ${d.synced || 0}，失败 ${d.failed || 0}`)
    fetchProducts()
  } catch {
    ElMessage.error('同步失败，请检查 ERP 配置')
  } finally {
    syncing.value = false
  }
}

async function fetchProducts() {
  loading.value = true
  try {
    const params = {
      page: filter.page,
      page_size: filter.page_size,
    }
    if (filter.keyword) params.keyword = filter.keyword
    const res = await getProducts(params)
    const d = res.data || {}
    allProducts.value = d.list || []
    total.value = d.total || 0
  } catch (e) {
    console.error('获取产品列表失败:', e)
    allProducts.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function viewDetail(row) {
  detailData.value = { ...row }
  detailVisible.value = true
}

function viewInventory(row) {
  ElMessage.warning('库存查询功能正在开发中')
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

onMounted(fetchProducts)
</script>

<style scoped>
.lark-products {
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

:deep(.product-detail-desc .el-descriptions__label) {
  width: 80px;
  font-weight: 500;
}

.price-text {
  color: #f56c6c;
  font-weight: 600;
}
</style>
