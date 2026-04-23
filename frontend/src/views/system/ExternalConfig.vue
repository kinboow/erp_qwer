<template>
  <div class="lark-external-config">
    <div class="lark-page-header">
      <div class="header-title">外部服务配置</div>
      <div class="header-desc">统一管理企业微信和 ERP 系统的连接与同步配置</div>
    </div>

    <div class="lark-table-panel">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="企微配置" name="wechat">
          <WechatConfig />
        </el-tab-pane>
        <el-tab-pane label="ERP 同步配置" name="erp">
          <ErpSyncConfig />
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import WechatConfig from './WechatConfig.vue'
import ErpSyncConfig from './ErpSyncConfig.vue'

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
  padding: 20px 24px;
}
</style>
