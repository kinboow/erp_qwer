<template>
  <div class="lark-external-config">
    <div class="lark-page-header">
      <div class="header-title">外部服务配置</div>
      <div class="header-desc">统一管理企业微信和 ERP 系统的连接与同步配置</div>
    </div>

    <div class="lark-table-panel">
      <el-tabs v-model="activeTab" class="config-tabs">
        <el-tab-pane name="wechat">
          <template #label>
            <span class="tab-label"><el-icon><ChatDotRound /></el-icon>企微配置</span>
          </template>
          <WechatConfig />
        </el-tab-pane>
        <el-tab-pane name="erp">
          <template #label>
            <span class="tab-label"><el-icon><DataLine /></el-icon>ERP 同步配置</span>
          </template>
          <ErpSyncConfig />
        </el-tab-pane>
        <el-tab-pane name="ai">
          <template #label>
            <span class="tab-label"><el-icon><Cpu /></el-icon>AI 模型配置</span>
          </template>
          <AiModelConfig />
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ChatDotRound, DataLine, Cpu } from '@element-plus/icons-vue'
import WechatConfig from './WechatConfig.vue'
import ErpSyncConfig from './ErpSyncConfig.vue'
import AiModelConfig from './AiModelConfig.vue'

const activeTab = ref('wechat')
</script>

<style scoped>
.lark-external-config {
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
  padding: 24px 28px;
}

.tab-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
}

:deep(.config-tabs > .el-tabs__header) {
  margin-bottom: 24px;
}

:deep(.config-tabs .el-tabs__item) {
  font-size: 14px;
  font-weight: 500;
}
</style>
