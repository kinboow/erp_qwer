<template>
  <div class="lark-sys-activities">
    <div class="lark-page-header">
      <div class="header-title">系统动态</div>
      <div class="header-desc">查看 ERP 同步失败等系统级事件详情</div>
    </div>

    <div class="lark-table-panel">
      <!-- 工具栏 -->
      <div class="lark-toolbar">
        <div class="toolbar-left">
          <el-select v-model="filter.type" placeholder="事件类型" clearable style="width: 120px;" @change="fetchList">
            <el-option label="全部" value="" />
            <el-option label="错误" value="error" />
            <el-option label="警告" value="warning" />
            <el-option label="信息" value="info" />
            <el-option label="成功" value="success" />
          </el-select>
          <el-select v-model="filter.source" placeholder="来源" clearable style="width: 140px;" @change="fetchList">
            <el-option label="全部" value="" />
            <el-option label="ERP 同步" value="erp_sync" />
            <el-option label="系统" value="system" />
          </el-select>
          <div class="lark-search-input-wrap">
            <el-icon class="search-icon"><Search /></el-icon>
            <input
              v-model="filter.keyword"
              class="lark-input"
              placeholder="搜索标题或内容"
              @keyup.enter="fetchList"
            />
          </div>
        </div>
        <div class="toolbar-right">
          <el-button :icon="Refresh" @click="fetchList" :loading="loading">刷新</el-button>
        </div>
      </div>

      <!-- 表格 -->
      <el-table :data="items" v-loading="loading" stripe class="lark-table">
        <el-table-column label="类型" prop="type" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="typeTagType(row.type)" size="small" effect="light">
              {{ typeLabel(row.type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="来源" prop="source" width="110" align="center">
          <template #default="{ row }">
            {{ sourceLabel(row.source) }}
          </template>
        </el-table-column>
        <el-table-column label="标题" prop="title" min-width="180" />
        <el-table-column label="详细内容" prop="content" min-width="360">
          <template #default="{ row }">
            <span class="activity-content">{{ row.content }}</span>
          </template>
        </el-table-column>
        <el-table-column label="时间" prop="created_at" width="180">
          <template #default="{ row }">
            <span class="log-time">{{ row.created_at }}</span>
          </template>
        </el-table-column>
      </el-table>

      <div class="lark-pagination">
        <el-pagination
          v-model:current-page="pagination.page"
          :page-size="pagination.pageSize"
          :total="pagination.total"
          layout="total, prev, pager, next"
          @current-change="fetchList"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { Search, Refresh } from '@element-plus/icons-vue'
import request from '@/utils/request'

const loading = ref(false)
const items = ref([])
const filter = reactive({ type: '', source: '', keyword: '' })
const pagination = reactive({ page: 1, pageSize: 20, total: 0 })

async function fetchList() {
  loading.value = true
  try {
    const params = { page: pagination.page, page_size: pagination.pageSize }
    if (filter.type) params.type = filter.type
    if (filter.source) params.source = filter.source
    if (filter.keyword) params.keyword = filter.keyword
    const res = await request({ url: '/api/system-activities', method: 'get', params })
    items.value = res.data?.items || []
    pagination.total = res.data?.total || 0
  } catch {
    items.value = []
    pagination.total = 0
  } finally {
    loading.value = false
  }
}

function typeTagType(type) {
  return { error: 'danger', warning: 'warning', info: 'info', success: 'success' }[type] || ''
}
function typeLabel(type) {
  return { error: '错误', warning: '警告', info: '信息', success: '成功' }[type] || type
}
function sourceLabel(source) {
  return { erp_sync: 'ERP 同步', system: '系统', wechat: '企业微信' }[source] || source || '-'
}

onMounted(() => {
  fetchList()
})
</script>

<style scoped>
.lark-sys-activities {
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
  width: 200px;
  transition: border-color 0.2s;
}

.lark-input:focus {
  border-color: var(--lark-primary);
}

.log-time {
  font-size: 13px;
  color: var(--lark-text-secondary);
  font-family: monospace;
}

.activity-content {
  color: var(--lark-text-secondary);
  word-break: break-word;
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
</style>
