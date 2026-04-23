<template>
  <div class="lark-room-listeners">
    <div class="lark-page-header">
      <div class="header-back" @click="router.push('/wechat-instances')">
        <el-icon><ArrowLeft /></el-icon>
        <span>返回实例列表</span>
      </div>
      <div class="header-title">群聊监听配置</div>
      <div class="header-desc">为企业微信实例配置需要监听和处理的群聊</div>
    </div>

    <div class="lark-table-panel">
      <!-- 工具栏 -->
      <div class="lark-toolbar">
        <div class="toolbar-left">
          <div class="lark-search-input-wrap">
            <el-icon class="search-icon"><Search /></el-icon>
            <input
              v-model="searchKeyword"
              class="lark-input"
              placeholder="搜索群聊名称或ID"
              @keyup.enter="handleSearch"
            />
            <el-icon v-if="searchKeyword" class="clear-icon" @click="clearSearch"><CircleClose /></el-icon>
          </div>
          <el-button class="lark-btn-secondary" @click="handleSearch">搜索</el-button>

          <el-select v-model="filterStatus" placeholder="所有状态" class="lark-select" @change="handleSearch" style="width: 120px; margin-left: 12px;">
            <el-option label="全部" value="" />
            <el-option label="已启用" :value="1" />
            <el-option label="已禁用" :value="0" />
          </el-select>
        </div>

        <div class="toolbar-right">
          <el-button
            type="primary"
            :icon="Refresh"
            @click="handleSync"
            :loading="syncLoading"
            class="sync-btn"
          >
            同步最新群聊
          </el-button>
        </div>
      </div>

      <!-- 批量操作栏 -->
      <div class="batch-bar" v-show="selectedRows.length > 0">
        <span class="selected-text">已选择 {{ selectedRows.length }} 个群聊</span>
        <div class="batch-actions">
          <el-button size="small" type="success" plain @click="handleBatchUpdate(1)">批量启用</el-button>
          <el-button size="small" type="danger" plain @click="handleBatchUpdate(0)">批量禁用</el-button>
        </div>
      </div>

      <!-- 数据表格 -->
      <el-table
        :data="tableData"
        style="width: 100%"
        v-loading="loading"
        class="lark-table"
        @selection-change="handleSelectionChange"
        :cell-style="{'border-bottom': '1px solid var(--lark-border-light)'}"
        :header-cell-style="{'border-bottom': '1px solid var(--lark-border-light)', 'background-color': 'var(--lark-bg-sidebar)', 'color': 'var(--lark-text-regular)', 'font-weight': '600'}"
      >
        <el-table-column type="selection" width="55" />

        <el-table-column label="群聊信息" min-width="250">
          <template #default="{ row }">
            <div class="room-cell">
              <div class="room-avatar">
                <el-icon :size="20" color="var(--lark-primary)"><ChatLineRound /></el-icon>
              </div>
              <div class="room-detail">
                <span class="room-name">{{ row.room_name }}</span>
                <span class="room-id">{{ row.room_id }}</span>
              </div>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="备注" min-width="200">
          <template #default="{ row }">
            <div class="desc-cell" @click="handleEditDesc(row)">
              <span v-if="row.description" class="desc-text">{{ row.description }}</span>
              <span v-else class="desc-empty">点击添加备注</span>
              <el-icon class="edit-icon"><Edit /></el-icon>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="监听状态" width="120">
          <template #default="{ row }">
            <el-switch
              v-model="row.is_enabled"
              :active-value="1"
              :inactive-value="0"
              @change="(val) => handleStatusChange(row, val)"
              style="--el-switch-on-color: #00B365;"
            />
          </template>
        </el-table-column>

        <el-table-column label="最后更新" width="160">
          <template #default="{ row }">
            <span class="time-text">{{ formatDate(row.updated_at) }}</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="lark-pagination">
        <span class="total-text">共 {{ pagination.total }} 个群聊</span>
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :total="pagination.total"
          :page-sizes="[20, 50, 100, 200]"
          layout="sizes, prev, pager, next, jumper"
          @size-change="fetchData"
          @current-change="fetchData"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, CircleClose, ArrowLeft, Refresh, ChatLineRound, Edit } from '@element-plus/icons-vue'
import { getListeners, updateListener, syncRooms, batchUpdateListeners } from '@/api/wechat'

const route = useRoute()
const router = useRouter()
const instanceId = route.params.instanceId

const loading = ref(false)
const syncLoading = ref(false)
const tableData = ref([])
const selectedRows = ref([])
const searchKeyword = ref('')
const filterStatus = ref('')

const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
})

const fetchData = async () => {
  if (!instanceId) return

  loading.value = true
  try {
    const res = await getListeners({
      instanceId,
      keyword: searchKeyword.value,
      isEnabled: filterStatus.value !== '' ? filterStatus.value : undefined,
      page: pagination.page,
      pageSize: pagination.pageSize
    })
    tableData.value = res.data.list
    pagination.total = res.data.total
  } catch (error) {
    console.error('获取失败:', error)
    ElMessage.error('获取群聊列表失败')
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  pagination.page = 1
  fetchData()
}

const clearSearch = () => {
  searchKeyword.value = ''
  handleSearch()
}

const handleSelectionChange = (rows) => {
  selectedRows.value = rows
}

const handleSync = async () => {
  syncLoading.value = true
  try {
    const res = await syncRooms(instanceId)
    const { total, synced, new: newCount } = res.data
    ElMessage.success(`同步完成！获取到 ${total} 个群聊，更新 ${synced} 个，新增 ${newCount} 个。`)
    fetchData()
  } catch (error) {
    console.error('同步失败:', error)
    ElMessage.error(error.response?.data?.message || '同步群聊失败，请检查实例是否在线')
  } finally {
    syncLoading.value = false
  }
}

const handleStatusChange = async (row, val) => {
  try {
    await updateListener(row.id, { isEnabled: val })
    ElMessage.success(`已${val === 1 ? '启用' : '禁用'}监听`)
  } catch (error) {
    // 恢复原状
    row.is_enabled = val === 1 ? 0 : 1
    ElMessage.error('状态更新失败')
  }
}

const handleBatchUpdate = async (isEnabled) => {
  if (selectedRows.value.length === 0) return

  const roomIds = selectedRows.value.map(row => row.room_id)
  const actionText = isEnabled === 1 ? '启用' : '禁用'

  ElMessageBox.confirm(`确定要批量${actionText}选中的 ${roomIds.length} 个群聊监听吗？`, '批量操作确认', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning',
    customClass: 'lark-confirm'
  }).then(async () => {
    try {
      loading.value = true
      await batchUpdateListeners({
        instanceId: Number(instanceId),
        roomIds,
        isEnabled
      })
      ElMessage.success(`批量${actionText}成功`)
      fetchData()
    } catch (error) {
      ElMessage.error('批量更新失败')
      loading.value = false
    }
  }).catch(() => {})
}

const handleEditDesc = (row) => {
  ElMessageBox.prompt('请输入群聊备注说明', '修改备注', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    inputValue: row.description || '',
    customClass: 'lark-confirm'
  }).then(async ({ value }) => {
    try {
      await updateListener(row.id, { description: value })
      row.description = value
      ElMessage.success('备注修改成功')
    } catch (error) {
      ElMessage.error('修改失败')
    }
  }).catch(() => {})
}

const formatDate = (dateStr) => {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

onMounted(() => {
  if (!instanceId) {
    ElMessage.warning('缺少实例ID参数')
    router.push('/wechat-instances')
    return
  }
  fetchData()
})
</script>

<style scoped>
.lark-room-listeners {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.lark-page-header {
  margin-bottom: 4px;
}

.header-back {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--lark-text-regular);
  font-size: 14px;
  cursor: pointer;
  margin-bottom: 12px;
  transition: color 0.2s;
}

.header-back:hover {
  color: var(--lark-primary);
}

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
}

.toolbar-left, .toolbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.batch-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  background-color: var(--lark-primary-light);
  border-radius: var(--lark-radius-sm);
  margin-bottom: 16px;
}

.selected-text {
  font-size: 14px;
  color: var(--lark-primary);
  font-weight: 500;
}

.batch-actions {
  display: flex;
  gap: 8px;
}

/* 搜索框 */
.lark-search-input-wrap {
  display: flex;
  align-items: center;
  background-color: var(--lark-bg-base);
  border: 1px solid var(--lark-border);
  border-radius: var(--lark-radius-sm);
  padding: 0 12px;
  height: 32px;
  width: 260px;
  transition: all 0.2s;
}

.lark-search-input-wrap:focus-within {
  border-color: var(--lark-primary);
  box-shadow: 0 0 0 2px var(--lark-primary-light);
}

.search-icon {
  color: var(--lark-text-secondary);
  margin-right: 8px;
}

.lark-input {
  border: none;
  background: transparent;
  outline: none;
  flex: 1;
  font-size: 14px;
  color: var(--lark-text-primary);
}

.clear-icon {
  color: var(--lark-text-disabled);
  cursor: pointer;
}

.lark-btn-secondary {
  background-color: var(--lark-bg-base);
  border: 1px solid var(--lark-border);
  color: var(--lark-text-primary);
}

.lark-table {
  --el-table-border: none;
  --el-table-border-color: transparent;
}

:deep(.el-table::before) {
  display: none;
}

.room-cell {
  display: flex;
  align-items: center;
  gap: 12px;
}

.room-avatar {
  width: 40px;
  height: 40px;
  background-color: var(--lark-primary-light);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.room-detail {
  display: flex;
  flex-direction: column;
}

.room-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--lark-text-primary);
  margin-bottom: 2px;
}

.room-id {
  font-size: 12px;
  color: var(--lark-text-secondary);
  font-family: monospace;
}

.desc-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 4px;
  transition: background-color 0.2s;
}

.desc-cell:hover {
  background-color: var(--lark-bg-hover);
}

.desc-cell:hover .edit-icon {
  opacity: 1;
}

.desc-text {
  font-size: 13px;
  color: var(--lark-text-regular);
}

.desc-empty {
  font-size: 13px;
  color: var(--lark-text-disabled);
  font-style: italic;
}

.edit-icon {
  color: var(--lark-primary);
  opacity: 0;
  transition: opacity 0.2s;
}

.time-text {
  font-size: 13px;
  color: var(--lark-text-regular);
}

.lark-pagination {
  margin-top: 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.total-text {
  font-size: 14px;
  color: var(--lark-text-secondary);
}
</style>
