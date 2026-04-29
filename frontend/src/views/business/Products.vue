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
            @input="debouncedSearch"
            @clear="handleSearch"
          />
        </div>
        <div class="toolbar-right">
          <el-button :icon="syncing ? undefined : Refresh" @click="handleSync" :loading="syncing">{{ syncing ? `同步产品中${trigger === 'scheduled' ? '（定时）' : ''}...` : '同步产品列表' }}</el-button>
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
        <el-table-column label="操作" width="250" fixed="right" align="center">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="viewDetail(row)">查看详情</el-button>
            <el-button type="primary" link size="small" @click="viewInventory(row)">查看库存</el-button>
            <el-button type="warning" link size="small" @click="openMappingDialog(row)">
              名称映射<el-badge v-if="row.mapping_count" :value="row.mapping_count" :max="99" class="mapping-badge" />
            </el-button>
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

    <!-- 名称映射弹窗 -->
    <el-dialog v-model="mappingVisible" :title="`名称映射 — ${mappingProductNo}`" width="560px" destroy-on-close>
      <div class="mapping-add-row">
        <el-input
          v-model="newAliasName"
          placeholder="输入映射名称后回车添加"
          clearable
          style="flex: 1"
          @keyup.enter="handleAddMapping"
        />
        <el-button type="primary" :loading="addingMapping" @click="handleAddMapping">添加</el-button>
      </div>
      <el-table :data="mappingList" v-loading="mappingLoading" stripe class="lark-table" style="margin-top: 12px" empty-text="暂无映射名称">
        <el-table-column type="index" label="#" width="50" align="center" />
        <el-table-column label="映射名称" prop="alias_name" min-width="200" />
        <el-table-column label="添加时间" prop="created_at" width="170" />
        <el-table-column label="操作" width="80" align="center">
          <template #default="{ row }">
            <el-popconfirm title="确定删除此映射？" @confirm="handleDeleteMapping(row.id)">
              <template #reference>
                <el-button type="danger" link size="small">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="mappingVisible = false">关闭</el-button>
      </template>
    </el-dialog>

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
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Search, Refresh } from '@element-plus/icons-vue'
import { getProducts, syncProducts, getNameMappings, addNameMapping, deleteNameMapping } from '@/api/products'
import { useSyncStatus } from '@/composables/useSyncStatus'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const allProducts = ref([])
const total = ref(0)
const detailVisible = ref(false)
const detailData = ref({})

const mappingVisible = ref(false)
const mappingProductNo = ref('')
const mappingList = ref([])
const mappingLoading = ref(false)
const newAliasName = ref('')
const addingMapping = ref(false)

const filter = reactive({
  keyword: '',
  page: 1,
  page_size: 50,
})


function handleSearch() {
  filter.page = 1
  fetchProducts()
}

let _searchTimer = null
function debouncedSearch() {
  clearTimeout(_searchTimer)
  _searchTimer = setTimeout(() => handleSearch(), 350)
}

const { syncing, trigger } = useSyncStatus('products', () => fetchProducts())

async function handleSync() {
  if (syncing.value) return
  syncing.value = true
  try {
    const res = await syncProducts()
    if (res.data?.already_syncing) {
      ElMessage.info('产品同步进行中，完成后将自动刷新')
    } else {
      ElMessage.success('同步已启动，完成后将自动刷新')
    }
  } catch {
    ElMessage.error('同步失败，请检查 ERP 配置')
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

async function openMappingDialog(row) {
  mappingProductNo.value = row.product_no
  mappingVisible.value = true
  newAliasName.value = ''
  await fetchMappings()
}

async function fetchMappings() {
  mappingLoading.value = true
  try {
    const res = await getNameMappings(mappingProductNo.value)
    mappingList.value = res.data || []
  } catch {
    mappingList.value = []
  } finally {
    mappingLoading.value = false
  }
}

async function handleAddMapping() {
  const name = newAliasName.value.trim()
  if (!name) return
  addingMapping.value = true
  try {
    const res = await addNameMapping(mappingProductNo.value, name)
    if (res.code === 200) {
      ElMessage.success('添加成功')
      newAliasName.value = ''
      await fetchMappings()
      fetchProducts()
    } else {
      ElMessage.warning(res.message || '添加失败')
    }
  } catch (e) {
    ElMessage.error(e?.message || '添加失败')
  } finally {
    addingMapping.value = false
  }
}

async function handleDeleteMapping(id) {
  try {
    await deleteNameMapping(id)
    ElMessage.success('已删除')
    await fetchMappings()
    fetchProducts()
  } catch {
    ElMessage.error('删除失败')
  }
}

function viewInventory(row) {
  router.push({ path: '/inventory', query: { product_no_exact: row.product_no } })
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
  if (route.query.keyword) {
    filter.keyword = String(route.query.keyword)
  }
  fetchProducts()
})
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

.mapping-add-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.mapping-badge {
  margin-left: 4px;
  vertical-align: middle;
}

:deep(.mapping-badge .el-badge__content) {
  font-size: 10px;
  height: 16px;
  line-height: 16px;
  padding: 0 4px;
}
</style>
