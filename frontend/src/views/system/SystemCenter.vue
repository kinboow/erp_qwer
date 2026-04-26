<template>
  <div class="lark-system-center">
    <div class="lark-table-panel">
      <el-tabs v-model="activeTab" class="center-tabs">
        <el-tab-pane name="messages">
          <template #label>
            <span class="tab-label"><el-icon><Bell /></el-icon>系统消息</span>
          </template>
          <SystemMessages />
        </el-tab-pane>
        <el-tab-pane name="activities">
          <template #label>
            <span class="tab-label"><el-icon><Monitor /></el-icon>系统动态</span>
          </template>
          <SystemActivities />
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import { Bell, Monitor } from '@element-plus/icons-vue'
import SystemMessages from './SystemMessages.vue'
import SystemActivities from './SystemActivities.vue'

const route = useRoute()
const activeTab = ref(route.meta?.tab || 'messages')
</script>

<style scoped>
.lark-system-center {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.lark-table-panel {
  background: var(--lark-bg-base);
  border-radius: var(--lark-radius-lg);
  padding: 20px 24px;
}

.tab-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
}

:deep(.center-tabs > .el-tabs__header) {
  margin-bottom: 16px;
}

:deep(.center-tabs .el-tabs__nav-wrap::after) {
  height: 1px;
}

:deep(.lark-sys-messages .lark-table-panel),
:deep(.lark-sys-activities .lark-panel) {
  padding: 0;
  background: transparent;
}
</style>
