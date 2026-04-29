<template>
  <div class="lark-erp-sync-config">
    <!-- 连接配置 -->
    <div class="config-card">
      <div class="card-title">
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
      <div class="form-actions">
        <el-button type="primary" @click="handleTestConnection" :loading="testing" :disabled="!form.erp_base_url">
          <el-icon><Connection /></el-icon>
          测试连接
        </el-button>
        <el-button type="success" @click="handleSave" :loading="saving" :disabled="!connectionTested">
          <el-icon><Check /></el-icon>
          保存配置
        </el-button>
      </div>
    </div>

    <!-- 同步状态 -->
    <div class="config-card">
      <div class="card-title">
        <el-icon><DataAnalysis /></el-icon>
        <span>同步状态</span>
        <el-button size="small" :icon="Refresh" @click="loadStatus" class="refresh-btn">刷新</el-button>
      </div>

      <div class="status-cards">
        <div class="status-card">
          <div class="sc-label">调度器</div>
          <div class="sc-value">
            <span class="sc-dot" :class="status.scheduler_running ? 'green' : 'gray'"></span>
            {{ status.scheduler_running ? '运行中' : '未启动' }}
          </div>
        </div>
        <div class="status-card">
          <div class="sc-label">当前状态</div>
          <div class="sc-value">
            <span class="sc-dot" :class="status.is_syncing ? 'orange' : 'gray'"></span>
            {{ status.is_syncing ? '同步中…' : '空闲' }}
          </div>
        </div>
        <div class="status-card">
          <div class="sc-label">自动同步</div>
          <div class="sc-value">
            <span class="sc-dot" :class="status.sync_enabled ? 'green' : 'red'"></span>
            {{ status.sync_enabled ? '已启用' : '已禁用' }}
          </div>
        </div>
      </div>

      <div v-if="status.last_result && Object.keys(status.last_result).length" class="last-sync-result">
        <div class="result-header">上次同步结果</div>
        <div class="result-cards">
          <div v-if="status.last_result.synced_at" class="result-card">
            <div class="rc-label">同步时间</div>
            <div class="rc-value">{{ status.last_result.synced_at }}</div>
          </div>
          <div v-if="status.last_result.total_found !== undefined" class="result-card">
            <div class="rc-label">发现订单</div>
            <div class="rc-value">{{ status.last_result.total_found }}</div>
          </div>
          <div v-if="status.last_result.synced !== undefined" class="result-card">
            <div class="rc-label">成功同步</div>
            <div class="rc-value success">{{ status.last_result.synced }}</div>
          </div>
          <div v-if="status.last_result.failed !== undefined" class="result-card">
            <div class="rc-label">失败</div>
            <div class="rc-value" :class="{ error: status.last_result.failed > 0 }">{{ status.last_result.failed }}</div>
          </div>
        </div>
        <div v-if="status.last_result.error" class="result-error">
          <el-icon><WarningFilled /></el-icon>
          <span>{{ status.last_result.error }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Connection, Check, Refresh, DataAnalysis, Upload, Plus, Loading, WarningFilled } from '@element-plus/icons-vue'
import { getErpSyncConfig, saveErpSyncConfig, testErpConnection, getErpSyncStatus, uploadErpQr, fetchQrImageUrl } from '@/api/erpSync'

const formRef = ref(null)
const saving = ref(false)
const testing = ref(false)
const uploading = ref(false)
const connectionTested = ref(false)
const qrPreviewUrl = ref('')

const form = reactive({
  erp_base_url: '',
  erp_username: '',
  erp_password: '',
  erp_qr_image_path: '',
})

const status = reactive({
  is_syncing: false,
  scheduler_running: false,
  sync_enabled: true,
  interval_minutes: 15,
  days_back: 360,
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
    status.days_back = s.days_back || 360
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
      connectionTested.value = false
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
  if (!connectionTested.value) {
    ElMessage.warning('请先测试连接成功后再保存配置')
    return
  }
  saving.value = true
  try {
    await saveErpSyncConfig({
      erp_base_url: form.erp_base_url,
      erp_username: form.erp_username,
      erp_password: form.erp_password,
      erp_qr_image_path: form.erp_qr_image_path,
    })
    ElMessage.success('配置已保存')
    await loadStatus()
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function handleTestConnection() {
  if (!form.erp_base_url) {
    ElMessage.warning('请先填写 ERP 服务地址')
    return
  }
  if (!form.erp_username || !form.erp_password) {
    ElMessage.warning('请先填写 ERP 登录账号和密码')
    return
  }
  if (!form.erp_qr_image_path) {
    ElMessage.warning('请先上传账套二维码')
    return
  }

  testing.value = true
  try {
    const res = await testErpConnection({
      erp_base_url: form.erp_base_url,
      erp_username: form.erp_username,
      erp_password: form.erp_password,
      erp_qr_image_path: form.erp_qr_image_path,
    }, { silentError: true })
    const data = res.data || {}
    const accountSetName = data.account_set_name || '未返回'
    connectionTested.value = true
    ElMessage.success(`连接测试成功，账套：${accountSetName}`)
  } catch (e) {
    connectionTested.value = false
    const msg = e?.message || e?.response?.data?.message || e?.response?.data?.detail
    ElMessage.error(msg || '连接测试失败')
  } finally {
    testing.value = false
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

watch(
  () => [form.erp_base_url, form.erp_username, form.erp_password, form.erp_qr_image_path],
  () => {
    connectionTested.value = false
  }
)
</script>

<style scoped>
.lark-erp-sync-config {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* 卡片区域 */
.config-card {
  background: var(--lark-bg-body, #f7f8fa);
  border-radius: 10px;
  padding: 24px;
}

.card-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: var(--lark-text-primary, #1f2329);
  margin-bottom: 20px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--lark-border-light, #eee);
}

.card-title .el-icon {
  font-size: 18px;
  color: var(--lark-primary, #3370ff);
}

.refresh-btn {
  margin-left: auto;
}

.config-form {
  max-width: 560px;
}

.form-row {
  display: flex;
  gap: 16px;
}

.form-col {
  flex: 1;
}

:deep(.el-form-item__label) {
  padding-bottom: 4px;
  font-weight: 500;
  font-size: 13px;
  color: var(--lark-text-primary);
}

.form-actions {
  display: flex;
  gap: 12px;
}

/* 状态卡片组 */
.status-cards {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.status-card {
  background: var(--lark-bg-base, #fff);
  border-radius: 10px;
  padding: 14px 18px;
  min-width: 130px;
  flex: 1;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}

.sc-label {
  font-size: 12px;
  color: var(--lark-text-secondary, #8f959e);
  margin-bottom: 8px;
}

.sc-value {
  font-size: 14px;
  font-weight: 500;
  color: var(--lark-text-primary, #1f2329);
  display: flex;
  align-items: center;
  gap: 6px;
}

.sc-value.num {
  font-size: 22px;
  font-weight: 700;
}

.sc-value.num small {
  font-size: 12px;
  font-weight: 400;
  color: var(--lark-text-secondary, #8f959e);
}

.sc-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.sc-dot.green { background-color: #00B365; box-shadow: 0 0 0 3px rgba(0,179,101,0.15); }
.sc-dot.orange { background-color: #FF8800; box-shadow: 0 0 0 3px rgba(255,136,0,0.15); }
.sc-dot.red { background-color: #F54A45; box-shadow: 0 0 0 3px rgba(245,74,69,0.15); }
.sc-dot.gray { background-color: #c0c4cc; }

/* 上次同步结果 */
.last-sync-result {
  margin-top: 20px;
  background: var(--lark-bg-base, #fff);
  border-radius: 10px;
  padding: 18px 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}

.result-header {
  font-size: 13px;
  font-weight: 600;
  color: var(--lark-text-secondary, #646a73);
  margin-bottom: 14px;
}

.result-cards {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.result-card {
  min-width: 110px;
  flex: 1;
}

.rc-label {
  font-size: 12px;
  color: var(--lark-text-secondary, #8f959e);
  margin-bottom: 4px;
}

.rc-value {
  font-size: 15px;
  font-weight: 600;
  color: var(--lark-text-primary, #1f2329);
}

.rc-value.success {
  color: #00B365;
}

.rc-value.error {
  color: #F54A45;
}

.result-error {
  margin-top: 12px;
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 14px;
  background: #fef0f0;
  border-radius: 8px;
  color: #F54A45;
  font-size: 13px;
  line-height: 1.5;
}

.result-error .el-icon {
  font-size: 16px;
  margin-top: 1px;
  flex-shrink: 0;
}

/* QR 相关（保留） */
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
