<template>
  <div class="lark-erp-sync-config">
    <div class="lark-page-header">
      <div class="header-title">ERP 同步配置</div>
      <div class="header-desc">配置弘兆云 ERP 连接信息和销售订单自动同步策略</div>
    </div>

    <!-- 连接配置 -->
    <div class="config-section">
      <div class="section-title">
        <el-icon><Connection /></el-icon>
        <span>ERP 连接配置</span>
      </div>

      <el-form :model="form" ref="formRef" label-position="top" class="config-form">
        <el-form-item label="ERP 服务地址" prop="erp_base_url" :rules="[{ required: true, message: '请输入 ERP 服务地址', trigger: 'blur' }]">
          <el-input v-model="form.erp_base_url" placeholder="如：http://nclouddl43.ywhzsoft.com:8154" />
        </el-form-item>

        <div class="form-row">
          <el-form-item label="登录账号" prop="erp_username" class="form-col">
            <el-input v-model="form.erp_username" placeholder="ERP 登录用户名" />
          </el-form-item>
          <el-form-item label="登录密码" prop="erp_password" class="form-col">
            <el-input v-model="form.erp_password" placeholder="ERP 登录密码" show-password />
          </el-form-item>
        </div>

        <el-form-item label="账套二维码图片路径" prop="erp_qr_image_path">
          <el-input v-model="form.erp_qr_image_path" placeholder="服务器上的二维码图片绝对路径（可选）" />
        </el-form-item>
      </el-form>
    </div>

    <!-- 同步策略 -->
    <div class="config-section">
      <div class="section-title">
        <el-icon><Timer /></el-icon>
        <span>同步策略</span>
      </div>

      <el-form :model="form" label-position="top" class="config-form">
        <div class="form-row">
          <el-form-item label="同步间隔（分钟）" class="form-col-sm">
            <el-input-number v-model="form.sync_interval_minutes" :min="1" :max="1440" />
          </el-form-item>
          <el-form-item label="同步天数范围" class="form-col-sm">
            <el-input-number v-model="form.sync_days_back" :min="1" :max="365" />
          </el-form-item>
          <el-form-item label="启用自动同步" class="form-col-sm">
            <el-switch v-model="form.sync_enabled" />
          </el-form-item>
        </div>
      </el-form>
    </div>

    <!-- 操作按钮 -->
    <div class="config-section">
      <div class="form-actions">
        <el-button type="primary" @click="handleSave" :loading="saving">
          <el-icon><Check /></el-icon>
          保存配置
        </el-button>
        <el-button type="warning" @click="handleTriggerSync" :loading="syncing" :disabled="!form.erp_base_url">
          <el-icon><Refresh /></el-icon>
          立即同步
        </el-button>
      </div>
    </div>

    <!-- 同步状态 -->
    <div class="config-section">
      <div class="section-title">
        <el-icon><DataAnalysis /></el-icon>
        <span>同步状态</span>
        <el-button size="small" :icon="Refresh" @click="loadStatus" style="margin-left: auto;">刷新</el-button>
      </div>

      <div class="status-grid">
        <div class="status-item">
          <span class="status-label">调度器</span>
          <el-tag :type="status.scheduler_running ? 'success' : 'info'" size="small">
            {{ status.scheduler_running ? '运行中' : '未启动' }}
          </el-tag>
        </div>
        <div class="status-item">
          <span class="status-label">当前状态</span>
          <el-tag :type="status.is_syncing ? 'warning' : 'info'" size="small">
            {{ status.is_syncing ? '同步中…' : '空闲' }}
          </el-tag>
        </div>
        <div class="status-item">
          <span class="status-label">自动同步</span>
          <el-tag :type="status.sync_enabled ? 'success' : 'danger'" size="small">
            {{ status.sync_enabled ? '已启用' : '已禁用' }}
          </el-tag>
        </div>
        <div class="status-item">
          <span class="status-label">同步间隔</span>
          <span class="status-value">{{ status.interval_minutes || '-' }} 分钟</span>
        </div>
        <div class="status-item">
          <span class="status-label">同步范围</span>
          <span class="status-value">最近 {{ status.days_back || '-' }} 天</span>
        </div>
      </div>

      <div v-if="status.last_result && Object.keys(status.last_result).length" class="last-sync-result">
        <div class="result-title">上次同步结果</div>
        <div class="result-grid">
          <div v-if="status.last_result.synced_at" class="result-item">
            <span class="result-label">时间</span>
            <span class="result-value">{{ status.last_result.synced_at }}</span>
          </div>
          <div v-if="status.last_result.total_found !== undefined" class="result-item">
            <span class="result-label">发现订单</span>
            <span class="result-value">{{ status.last_result.total_found }}</span>
          </div>
          <div v-if="status.last_result.synced !== undefined" class="result-item">
            <span class="result-label">成功同步</span>
            <span class="result-value success">{{ status.last_result.synced }}</span>
          </div>
          <div v-if="status.last_result.failed !== undefined" class="result-item">
            <span class="result-label">失败</span>
            <span class="result-value" :class="{ error: status.last_result.failed > 0 }">{{ status.last_result.failed }}</span>
          </div>
          <div v-if="status.last_result.error" class="result-item full">
            <span class="result-label">错误</span>
            <span class="result-value error">{{ status.last_result.error }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Connection, Check, Refresh, Timer, DataAnalysis } from '@element-plus/icons-vue'
import { getErpSyncConfig, saveErpSyncConfig, getErpSyncStatus, triggerErpSync } from '@/api/erpSync'

const formRef = ref(null)
const saving = ref(false)
const syncing = ref(false)

const form = reactive({
  erp_base_url: '',
  erp_username: '',
  erp_password: '',
  erp_qr_image_path: '',
  sync_interval_minutes: 15,
  sync_days_back: 90,
  sync_enabled: true,
})

const status = reactive({
  is_syncing: false,
  scheduler_running: false,
  sync_enabled: true,
  interval_minutes: 15,
  days_back: 90,
  last_result: {},
})

async function loadConfig() {
  try {
    const res = await getErpSyncConfig()
    const cfg = res.data || {}
    form.erp_base_url = cfg.erp_base_url || ''
    form.erp_username = cfg.erp_username || ''
    form.erp_password = cfg.erp_password || ''
    form.erp_qr_image_path = cfg.erp_qr_image_path || ''
    form.sync_interval_minutes = cfg.sync_interval_minutes || 15
    form.sync_days_back = cfg.sync_days_back || 90
    form.sync_enabled = cfg.sync_enabled !== false
  } catch { /* first load, no config yet */ }
}

async function loadStatus() {
  try {
    const res = await getErpSyncStatus()
    const s = res.data || {}
    status.is_syncing = s.is_syncing || false
    status.scheduler_running = s.scheduler_running || false
    status.sync_enabled = s.sync_enabled !== false
    status.interval_minutes = s.interval_minutes || 15
    status.days_back = s.days_back || 90
    status.last_result = s.last_result || {}
  } catch { /* ignore */ }
}

async function handleSave() {
  saving.value = true
  try {
    await saveErpSyncConfig({
      erp_base_url: form.erp_base_url,
      erp_username: form.erp_username,
      erp_password: form.erp_password,
      erp_qr_image_path: form.erp_qr_image_path,
      sync_interval_minutes: form.sync_interval_minutes,
      sync_days_back: form.sync_days_back,
      sync_enabled: form.sync_enabled,
    })
    ElMessage.success('配置已保存')
    await loadStatus()
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function handleTriggerSync() {
  syncing.value = true
  try {
    const res = await triggerErpSync(form.sync_days_back)
    const data = res.data || {}
    ElMessage.success(`同步完成：${data.synced || 0} 成功，${data.failed || 0} 失败`)
    await loadStatus()
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || '同步失败')
  } finally {
    syncing.value = false
  }
}

onMounted(async () => {
  await loadConfig()
  await loadStatus()
})
</script>

<style scoped>
.lark-erp-sync-config {
  max-width: 800px;
  margin: 0 auto;
  padding: 24px;
}

.lark-page-header {
  margin-bottom: 24px;
}

.header-title {
  font-size: 20px;
  font-weight: 600;
  color: #1f2329;
}

.header-desc {
  font-size: 13px;
  color: #8f959e;
  margin-top: 4px;
}

.config-section {
  background: #fff;
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 16px;
  border: 1px solid #e5e6eb;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: #1f2329;
  margin-bottom: 16px;
}

.config-form {
  max-width: 600px;
}

.form-row {
  display: flex;
  gap: 16px;
}

.form-col {
  flex: 1;
}

.form-col-sm {
  flex: 0 0 auto;
}

.form-actions {
  display: flex;
  gap: 12px;
}

.status-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
}

.status-item {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 140px;
}

.status-label {
  font-size: 13px;
  color: #8f959e;
}

.status-value {
  font-size: 13px;
  font-weight: 500;
  color: #1f2329;
}

.last-sync-result {
  margin-top: 16px;
  padding: 12px;
  background: #f7f8fa;
  border-radius: 6px;
}

.result-title {
  font-size: 13px;
  font-weight: 600;
  color: #646a73;
  margin-bottom: 8px;
}

.result-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 24px;
}

.result-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.result-item.full {
  flex-basis: 100%;
}

.result-label {
  font-size: 12px;
  color: #8f959e;
}

.result-value {
  font-size: 13px;
  font-weight: 500;
  color: #1f2329;
}

.result-value.success {
  color: #00b42a;
}

.result-value.error {
  color: #f53f3f;
}
</style>
