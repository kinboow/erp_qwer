<template>
  <div class="lark-external-config">
    <div class="lark-page-header">
      <div class="header-title">外部服务配置</div>
      <div class="header-desc">统一管理企业微信和 ERP 系统的连接与同步配置</div>
    </div>

    <div class="lark-table-panel">
      <el-tabs v-model="activeTab" class="config-tabs" @tab-change="handleTabChange">
        <el-tab-pane name="wechat">
          <template #label>
            <span class="tab-label"><el-icon><ChatDotRound /></el-icon>企微配置</span>
          </template>
          <WechatConfig v-if="activeTab === 'wechat'" />
        </el-tab-pane>
        <el-tab-pane name="erp">
          <template #label>
            <span class="tab-label"><el-icon><DataLine /></el-icon>ERP 同步配置</span>
          </template>
          <ErpSyncConfig v-if="activeTab === 'erp'" />
        </el-tab-pane>
        <el-tab-pane name="ai">
          <template #label>
            <span class="tab-label"><el-icon><Cpu /></el-icon>AI 模型配置</span>
          </template>
          <AiModelConfig v-if="activeTab === 'ai'" />
        </el-tab-pane>
        <el-tab-pane name="printer">
          <template #label>
            <span class="tab-label"><el-icon><Printer /></el-icon>打印机测试</span>
          </template>
          <PrinterConfig v-if="activeTab === 'printer'" />
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ChatDotRound, DataLine, Cpu, Printer } from '@element-plus/icons-vue'
import WechatConfig from './WechatConfig.vue'
import ErpSyncConfig from './ErpSyncConfig.vue'
import AiModelConfig from './AiModelConfig.vue'
import PrinterConfig from './PrinterConfig.vue'

const route = useRoute()
const router = useRouter()
const activeTab = ref(route.meta.tab || 'wechat')

const TAB_ROUTES = { wechat: '/config-wechat', erp: '/config-erp', ai: '/config-ai', printer: '/config-printer' }

function handleTabChange(tab) {
  const target = TAB_ROUTES[tab]
  if (target && route.path !== target) {
    router.push(target)
  }
}
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
