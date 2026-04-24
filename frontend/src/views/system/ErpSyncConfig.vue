<template>
  <div class="lark-erp-sync-config">
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
import { Connection, Check, Refresh, Timer, DataAnalysis, Upload, Plus, Loading } from '@element-plus/icons-vue'
import { getErpSyncConfig, saveErpSyncConfig, getErpSyncStatus, triggerErpSync, uploadErpQr, fetchQrImageUrl } from '@/api/erpSync'

const formRef = ref(null)
const saving = ref(false)
const syncing = ref(false)
const uploading = ref(false)
const qrPreviewUrl = ref('')

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

function handleBeforeUpload(file) {
  const isImage = file.type.startsWith('image/')
  const isLt5M = file.size / 1024 / 1024 < 5
  if (!isImage) { ElMessage.error('只能上传图片文件'); return false }
  if (!isLt5M) { ElMessage.error('图片大小不能超过 5MB'); return false }
  return true
}

async function handleUploadQr({ file }) {
  uploading.value = true
  try {
    const res = await uploadErpQr(file)
    const url = res.data?.url
    if (url) {
      form.erp_qr_image_path = url
      await loadQrPreview()
      ElMessage.success('账套二维码上传成功')
    } else {
      ElMessage.error('上传失败')
    }
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || '上传失败')
  } finally {
    uploading.value = false
  }
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

async function loadQrPreview() {
  try {
    // 释放旧的 blob URL
    if (qrPreviewUrl.value) URL.revokeObjectURL(qrPreviewUrl.value)
    qrPreviewUrl.value = await fetchQrImageUrl()
  } catch {
    qrPreviewUrl.value = ''
  }
}

onMounted(async () => {
  await loadConfig()
  await loadStatus()
  if (form.erp_qr_image_path) await loadQrPreview()
})
</script>

<style scoped>
.lark-erp-sync-config {
}

.config-section {
  padding: 0 0 20px;
  margin-bottom: 16px;
  border-bottom: 1px solid var(--lark-border-light, #f0f0f0);
}

.config-section:last-child {
  border-bottom: none;
  margin-bottom: 0;
  padding-bottom: 0;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: var(--lark-text-primary, #1f2329);
  margin-bottom: 20px;
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

.qr-upload-area {
  position: relative;
}

.qr-preview {
  position: relative;
  width: 148px;
  height: 148px;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--lark-border-light, #e5e6eb);
  cursor: pointer;
}

.qr-image {
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: #fafafa;
}

.qr-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  background: rgba(0, 0, 0, 0.5);
  color: #fff;
  font-size: 12px;
  opacity: 0;
  transition: opacity 0.2s;
}

.qr-preview:hover .qr-overlay {
  opacity: 1;
}

.qr-placeholder {
  width: 148px;
  height: 148px;
  border: 1px dashed #d9d9d9;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  cursor: pointer;
  color: #8f959e;
  font-size: 12px;
  transition: border-color 0.2s;
}

.qr-placeholder:hover {
  border-color: var(--el-color-primary);
}

.qr-uploading {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
  font-size: 12px;
  color: #8f959e;
}
</style>
