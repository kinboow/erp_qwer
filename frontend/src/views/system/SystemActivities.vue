<template>
  <div class="lark-sys-activities">
    <div class="lark-panel">
      <!-- 工具栏 -->
      <div class="lark-toolbar">
        <div class="toolbar-left">
          <div class="lark-search-input-wrap">
            <el-icon class="search-icon"><Search /></el-icon>
            <input
              v-model="keyword"
              class="lark-input"
              placeholder="搜索动态内容"
              @keyup.enter="fetchList"
            />
          </div>
        </div>
        <div class="toolbar-right">
          <el-button :icon="Refresh" @click="fetchList" :loading="loading">刷新</el-button>
        </div>
      </div>

      <!-- 时间轴 -->
      <div v-loading="loading">
        <div v-if="items.length === 0" class="empty-activity">暂无动态</div>
        <div v-else class="lark-timeline">
          <div class="timeline-item" v-for="(item, index) in items" :key="index">
            <div class="timeline-dot" :class="item.type"></div>
            <div class="timeline-content">
              <div class="timeline-text">{{ item.content }}</div>
              <div class="timeline-time">{{ item.time }}</div>
            </div>
          </div>
        </div>
      </div>

      <div class="lark-pagination" v-if="pagination.total > pagination.pageSize">
        <el-pagination
          v-model:current-page="pagination.page"
          :page-size="pagination.pageSize"
          :total="pagination.total"
          layout="total, sizes, prev, pager, next, jumper"
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
const keyword = ref('')
const pagination = reactive({ page: 1, pageSize: 30, total: 0 })

async function fetchList() {
  loading.value = true
  try {
    const params = { page: pagination.page, page_size: pagination.pageSize }
    if (keyword.value) params.keyword = keyword.value
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

.lark-panel {
  background: var(--lark-bg-base);
  border-radius: var(--lark-radius-lg);
  padding: 20px 24px;
}

.lark-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
  gap: 12px;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
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
  width: 280px;
  transition: border-color 0.2s;
}

.lark-input:focus {
  border-color: var(--lark-primary);
}

.empty-activity {
  text-align: center;
  color: var(--lark-text-disabled);
  padding: 48px 0;
  font-size: 14px;
}

/* 时间轴 */
.lark-timeline {
  position: relative;
  padding-left: 20px;
}

.lark-timeline::before {
  content: '';
  position: absolute;
  left: 3px;
  top: 6px;
  bottom: 6px;
  width: 2px;
  background-color: var(--lark-border-light);
}

.timeline-item {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding-bottom: 24px;
  position: relative;
}

.timeline-item:last-child {
  padding-bottom: 0;
}

.timeline-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: var(--lark-border);
  margin-top: 6px;
  position: relative;
  z-index: 1;
  flex-shrink: 0;
}

.timeline-dot.urgent { background-color: #F56C6C; box-shadow: 0 0 0 3px #fde2e2; }
.timeline-dot.important { background-color: #E6A23C; box-shadow: 0 0 0 3px #faecd8; }
.timeline-dot.normal { background-color: #00B365; }

.timeline-content {
  flex: 1;
}

.timeline-text {
  font-size: 14px;
  color: var(--lark-text-primary);
  margin-bottom: 4px;
  line-height: 1.5;
  word-break: break-word;
}

.timeline-time {
  font-size: 12px;
  color: var(--lark-text-disabled);
  font-family: monospace;
}

.lark-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 20px;
}
</style>
