<template>
  <div class="lark-wechat-config">
    <!-- 连接配置 -->
    <div class="config-section">
      <div class="section-title">
        <el-icon><Connection /></el-icon>
        <span>API 连接配置</span>
      </div>

      <el-form
        :model="configForm"
        :rules="rules"
        ref="formRef"
        label-position="top"
        class="config-form"
      >
        <div class="form-row">
          <el-form-item label="服务器地址" prop="host" class="form-col">
            <el-input v-model="configForm.host" placeholder="如：192.168.1.100">
              <template #prepend>http://</template>
            </el-input>
          </el-form-item>

          <el-form-item label="端口" prop="port" class="form-col-sm">
            <el-input v-model="configForm.port" placeholder="如：9000" />
          </el-form-item>
        </div>

        <el-form-item label="API 密钥 (X-API-Key)" prop="apiKey">
          <el-input v-model="configForm.apiKey" placeholder="选填，留空则不使用密钥认证" show-password />
        </el-form-item>

        <div class="form-actions">
          <el-button type="primary" @click="handleTestConnection" :loading="testing">
            <el-icon><Connection /></el-icon>
            测试连接
          </el-button>
          <el-button type="success" @click="handleSave" :loading="saving" :disabled="!connectionTested">
            <el-icon><Check /></el-icon>
            保存配置
          </el-button>
        </div>
      </el-form>

      <!-- 连接测试结果 -->
      <div v-if="testResult" class="test-result" :class="testResult.success ? 'success' : 'error'">
        <el-icon v-if="testResult.success"><SuccessFilled /></el-icon>
        <el-icon v-else><CircleCloseFilled /></el-icon>
        <div class="test-info">
          <div class="test-title">{{ testResult.success ? '连接成功' : '连接失败' }}</div>
          <div class="test-detail">{{ testResult.message }}</div>
        </div>
      </div>
    </div>

    <!-- 实例选择 -->
    <div class="config-section">
      <div class="section-title">
        <el-icon><Monitor /></el-icon>
        <span>实例选择</span>
        <el-button size="small" :icon="Plus" type="primary" @click="handleAddInstance" :loading="startingInstance" :disabled="!hasApiConfig" style="margin-left: auto;">
          新增实例
        </el-button>
        <el-button size="small" :icon="Refresh" @click="handleFetchInstances" :loading="fetchingInstances">
          刷新实例
        </el-button>
      </div>

      <div v-if="!hasApiConfig" class="empty-hint">
        请先配置并保存 API 连接信息
      </div>

      <div v-else-if="fetchingInstances" v-loading="true" style="min-height: 100px;"></div>

      <div v-else-if="instances.length === 0" class="empty-hint">
        未检测到任何实例，请确认企业微信服务已启动
      </div>

      <div v-else-if="runningInstances.length === 0" class="empty-hint">
        未检测到运行中的实例，请确认企业微信服务已启动
      </div>

      <div v-else class="instance-list">
        <div
          v-for="inst in runningInstances"
          :key="inst.wxid || `client-${inst.client_id || inst.pid}`"
          class="instance-item"
          :class="{ selected: selectedWxid === inst.wxid, disabled: !inst.wxid }"
          @click="handleSelectInstance(inst)"
        >
          <div class="inst-left">
            <div class="inst-avatar" :class="getInstanceStatusClass(inst)">
              <img v-if="inst.avatar" :src="inst.avatar" alt="avatar" class="inst-avatar-image" />
              <el-icon v-else :size="18"><User /></el-icon>
            </div>
            <div class="inst-info">
              <div class="inst-name">{{ inst.nickname || inst.wxid || `实例 ${inst.client_id || inst.pid || '-'}` }}</div>
              <div v-if="inst.phone" class="inst-meta">手机号：{{ inst.phone }}</div>
              <div class="inst-wxid">{{ inst.wxid || '未登录，暂无 wxid' }}</div>
            </div>
          </div>
          <div class="inst-right">
            <div class="inst-status-group">
              <span class="inst-status" :class="inst.login_status ? 'online' : 'offline'">
                {{ inst.login_status ? '已登录' : '未登录' }}
              </span>
              <span class="inst-status" :class="inst.status ? 'online' : 'offline'">
                {{ inst.status ? '运行中' : '未运行' }}
              </span>
              <span class="inst-status" :class="inst.attached ? 'online' : 'offline'">
                {{ inst.attached ? '已连接' : '未连接' }}
              </span>
            </div>
            <el-button
              v-if="canShowLoginButton(inst)"
              size="small"
              type="primary"
              link
              :loading="screenshotLoading && currentLoginInstanceKey === getInstanceRuntimeKey(inst)"
              @click.stop="handleLoginInstance(inst)"
            >
              登录
            </el-button>
            <el-icon v-if="selectedWxid === inst.wxid && inst.wxid" color="var(--lark-primary)"><Select /></el-icon>
            <span v-else-if="!inst.wxid && !canShowLoginButton(inst)" class="inst-disabled-text">
              需先登录
            </span>
          </div>
        </div>
      </div>

      <div v-if="instances.length > 0" class="instance-summary">
        <div class="summary-item">
          <span class="summary-label">实例总数</span>
          <span class="summary-value">{{ instances.length }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">已登录</span>
          <span class="summary-value success">{{ loggedInCount }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">运行中</span>
          <span class="summary-value">{{ runningCount }}</span>
        </div>
      </div>

      <!-- 已绑定实例信息 -->
      <div v-if="savedInstance" class="bound-info">
        <el-icon color="var(--lark-primary)"><InfoFilled /></el-icon>
        <span>当前绑定实例：<strong>{{ savedInstance.name || savedInstance.wxid }}</strong></span>
      </div>


    </div>

    <!-- 登录二维码弹窗 -->
    <el-dialog
      v-model="qrDialogVisible"
      title="扫码登录企业微信"
      width="420px"
      :close-on-click-modal="false"
      @closed="handleQrDialogClosed"
      align-center
    >
      <div class="qr-dialog-body">
        <div v-if="qrLoading" v-loading="true" class="qr-loading">{{ qrDisplayMode === 'screenshot' ? '正在获取窗口截图…' : '正在获取登录二维码…' }}</div>
        <div v-else-if="qrError" class="qr-error">
          <el-icon :size="48" color="var(--el-color-danger)"><CircleCloseFilled /></el-icon>
          <div class="qr-error-text">{{ qrError }}</div>
          <el-button type="primary" size="small" @click="handleRetryQr">重试</el-button>
        </div>
        <div v-else-if="qrImageUrl" class="qr-code-wrapper">
          <img :src="qrImageUrl" alt="登录二维码" class="qr-code-image" />
          <div class="qr-hint">{{ qrDisplayMode === 'screenshot' ? '请在企业微信窗口中完成扫码登录' : '请使用企业微信扫描二维码登录' }}</div>
          <div v-if="qrDisplayMode === 'qrcode'" class="qr-countdown">二维码将在 <strong>{{ qrCountdown }}</strong> 秒后自动刷新</div>
          <div v-else class="qr-countdown">当前展示的是该实例窗口截图，PID：<strong>{{ screenshotPid || '-' }}</strong></div>
        </div>
        <div v-else class="qr-loading">等待中…</div>
      </div>
      <template #footer>
        <el-button @click="qrDialogVisible = false">关闭</el-button>
        <el-button v-if="qrDisplayMode === 'qrcode'" type="primary" @click="handleManualRefreshQr" :loading="qrRefreshing">刷新二维码</el-button>
        <el-button v-else type="primary" @click="handleRefreshLoginScreenshot" :loading="screenshotLoading">刷新截图</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Connection, Check, Refresh, Monitor, User, Select,
  SuccessFilled, CircleCloseFilled, InfoFilled, Plus
} from '@element-plus/icons-vue'
import { getInstances, createInstance, updateInstance, getWechatGlobalConfig, saveWechatGlobalConfig, proxyStartWechat, proxyWaitLogin, proxyRefreshQrcode, proxyLoginWindowScreenshot } from '@/api/wechat'
import request from '@/utils/request'

const formRef = ref(null)
const testing = ref(false)
const saving = ref(false)
const fetchingInstances = ref(false)
const connectionTested = ref(false)
const testResult = ref(null)
const instances = ref([])
const selectedWxid = ref('')
const savedInstance = ref(null)

const startingInstance = ref(false)
const qrDialogVisible = ref(false)
const qrLoading = ref(false)
const qrRefreshing = ref(false)
const qrError = ref('')
const qrImageUrl = ref('')
const qrCountdown = ref(60)
const qrWxid = ref('')
const qrDisplayMode = ref('qrcode')
const screenshotLoading = ref(false)
const screenshotPid = ref(null)
const currentLoginInstanceKey = ref('')
const currentLoginInstance = ref(null)
let qrRefreshTimer = null
let qrCountdownTimer = null

const configForm = reactive({
  host: '',
  port: '',
  apiKey: ''
})

const rules = {
  host: [{ required: true, message: '请输入服务器地址', trigger: 'blur' }],
  port: [{ required: true, message: '请输入端口', trigger: 'blur' }]
}

const apiBaseUrl = computed(() => {
  if (!configForm.host || !configForm.port) return ''
  return `http://${configForm.host}:${configForm.port}`
})
const appOrigin = computed(() => {
  if (typeof window === 'undefined' || !window.location?.origin) return ''
  return window.location.origin
})
const compatHttpUrl = computed(() => {
  if (!appOrigin.value) return ''
  return `${appOrigin.value}/sync?wxid={wxid}`
})
const compatWsUrl = computed(() => {
  if (!appOrigin.value) return ''
  const wsOrigin = appOrigin.value.replace(/^http:/i, 'ws:').replace(/^https:/i, 'wss:')
  return `${wsOrigin}/ws?wxid={wxid}`
})

const configLoaded = ref(false)
const hasApiConfig = computed(() => configLoaded.value && !!(configForm.host && configForm.port))
const runningInstances = computed(() => instances.value.filter(item => item.status))
const loggedInCount = computed(() => instances.value.filter(item => item.login_status).length)
const runningCount = computed(() => runningInstances.value.length)

const getInstanceStatusClass = (inst) => {
  if (inst.login_status) return 'online'
  if (inst.status || inst.attached) return 'pending'
  return 'offline'
}

const getInstanceRuntimeKey = (inst) => String(inst.wxid || inst.client_id || inst.pid || '')

const canShowLoginButton = (inst) => !!inst?.status && !inst?.login_status && !!(inst?.pid || inst?.client_id || inst?.wxid)

async function loadConfig() {
  try {
    const res = await getWechatGlobalConfig()
    const cfg = res.data || {}
    configForm.host = cfg.host || ''
    configForm.port = cfg.port || ''
    configForm.apiKey = cfg.api_key || ''
    selectedWxid.value = cfg.selected_wxid || ''
    if (cfg.bound_instance_id) {
      savedInstance.value = {
        id: cfg.bound_instance_id,
        wxid: cfg.selected_wxid || '',
        name: cfg.bound_instance_name || ''
      }
    }
    if (configForm.host && configForm.port) {
      connectionTested.value = true
      configLoaded.value = true
    }
  } catch { /* first time, no config yet */ }
}

async function saveConfigToDb(extraFields = {}) {
  await saveWechatGlobalConfig({
    host: configForm.host,
    port: configForm.port,
    api_key: configForm.apiKey,
    selected_wxid: selectedWxid.value,
    ws_path: '/ws/wechat/messages',
    http_path: '/api/wechat/callback/http',
    callback_timeout: 5,
    ...extraFields
  })
  configLoaded.value = true
}

async function copyText(text) {
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制到剪贴板')
  } catch (error) {
    ElMessage.error('复制失败')
  }
}

async function handleTestConnection() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return

    testing.value = true
    testResult.value = null

    try {
      await request({
        url: '/api/wechat/proxy/health',
        method: 'post',
        data: { api_base_url: apiBaseUrl.value, api_key: configForm.apiKey || null }
      })

      testResult.value = { success: true, message: `API 服务正常 (${apiBaseUrl.value})` }
      connectionTested.value = true
    } catch (error) {
      testResult.value = { success: false, message: error?.response?.data?.message || error.message || '无法连接到服务器' }
      connectionTested.value = false
    } finally {
      testing.value = false
    }
  })
}

async function handleSave() {
  saving.value = true
  try {
    let boundId = null
    let boundName = ''

    if (selectedWxid.value) {
      const existing = await getInstances()
      const list = existing.data || []
      const found = list.find(i => i.wxid === selectedWxid.value)
      let savedInstanceId = found?.id || null

      if (found) {
        await updateInstance(found.id, {
          name: found.name,
          api_base_url: apiBaseUrl.value,
          api_key: configForm.apiKey || null
        })
      } else {
        const inst = instances.value.find(i => i.wxid === selectedWxid.value)
        const created = await createInstance({
          wxid: selectedWxid.value,
          name: inst?.nickname || selectedWxid.value,
          api_base_url: apiBaseUrl.value,
          api_key: configForm.apiKey || null
        })
        savedInstanceId = created.data?.id || null
      }

      const instData = instances.value.find(i => i.wxid === selectedWxid.value)
      const existingInst = list.find(i => i.wxid === selectedWxid.value)
      boundId = existingInst?.id || found?.id || savedInstanceId
      boundName = instData?.nickname || selectedWxid.value
      savedInstance.value = { id: boundId, wxid: selectedWxid.value, name: boundName }
    }

    await saveConfigToDb({
      bound_instance_id: boundId,
      bound_instance_name: boundName
    })

    ElMessage.success('配置已保存，消息接收已自动开启')
    handleFetchInstances()
  } catch (error) {
    ElMessage.error(error?.response?.data?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function handleFetchInstances() {
  if (!apiBaseUrl.value) {
    ElMessage.warning('请先填写服务器地址和端口')
    return
  }

  fetchingInstances.value = true
  try {
    const res = await request({
      url: '/api/wechat/proxy/overview',
      method: 'post',
      data: { api_base_url: apiBaseUrl.value, api_key: configForm.apiKey || null }
    })
    instances.value = Array.isArray(res.data) ? res.data : []
    if (instances.value.length > 0 && (!selectedWxid.value || !instances.value.some(item => item.wxid === selectedWxid.value))) {
      const attached = instances.value.find(i => i.login_status && i.wxid) || instances.value.find(i => i.attached && i.wxid) || instances.value.find(i => i.wxid)
      if (attached) selectedWxid.value = attached.wxid
    }
  } catch (error) {
    ElMessage.error('获取实例列表失败: ' + (error?.response?.data?.message || error.message))
    instances.value = []
  } finally {
    fetchingInstances.value = false
  }
}

function handleSelectInstance(inst) {
  if (!inst.wxid) {
    ElMessage.warning('该实例尚未登录，暂时无法绑定')
    return
  }
  selectedWxid.value = inst.wxid
}

function clearQrTimers() {
  if (qrRefreshTimer) { clearInterval(qrRefreshTimer); qrRefreshTimer = null }
  if (qrCountdownTimer) { clearInterval(qrCountdownTimer); qrCountdownTimer = null }
}

function resetLoginDialogState() {
  qrError.value = ''
  qrImageUrl.value = ''
  qrWxid.value = ''
  qrDisplayMode.value = 'qrcode'
  screenshotPid.value = null
}

function startQrCountdown() {
  qrCountdown.value = 60
  if (qrCountdownTimer) clearInterval(qrCountdownTimer)
  qrCountdownTimer = setInterval(() => {
    qrCountdown.value--
    if (qrCountdown.value <= 0) {
      clearInterval(qrCountdownTimer)
      qrCountdownTimer = null
    }
  }, 1000)
}

function startQrAutoRefresh() {
  clearQrTimers()
  startQrCountdown()
  qrRefreshTimer = setInterval(async () => {
    await doRefreshQr()
    startQrCountdown()
  }, 60000)
}

async function doRefreshQr() {
  if (!qrWxid.value) return
  try {
    const res = await proxyRefreshQrcode({
      api_base_url: apiBaseUrl.value,
      api_key: configForm.apiKey || null,
      wxid: qrWxid.value
    })
    const data = res.data || {}
    if (data.qrcode) {
      qrImageUrl.value = data.qrcode.startsWith('data:') ? data.qrcode : `data:image/png;base64,${data.qrcode}`
      qrError.value = ''
    } else if (data.qr_url) {
      qrImageUrl.value = data.qr_url
      qrError.value = ''
    } else {
      qrError.value = '未获取到二维码数据'
    }
  } catch (e) {
    qrError.value = e?.response?.data?.message || '刷新二维码失败'
  }
}

async function handleAddInstance() {
  if (!apiBaseUrl.value) {
    ElMessage.warning('请先配置 API 连接信息')
    return
  }

  startingInstance.value = true
  qrDialogVisible.value = true
  qrLoading.value = true
  resetLoginDialogState()
  currentLoginInstance.value = null
  currentLoginInstanceKey.value = ''
  clearQrTimers()

  try {
    const startRes = await proxyStartWechat({
      api_base_url: apiBaseUrl.value,
      api_key: configForm.apiKey || null,
      force_new: true
    })
    const startData = startRes.data || {}
    const wxid = startData.wxid || startData.client_id || startData.pid || ''
    if (!wxid) {
      qrError.value = '启动成功但未返回实例标识'
      qrLoading.value = false
      startingInstance.value = false
      return
    }
    qrWxid.value = String(wxid)
    qrDisplayMode.value = 'qrcode'

    const loginRes = await proxyWaitLogin({
      api_base_url: apiBaseUrl.value,
      api_key: configForm.apiKey || null,
      wxid: qrWxid.value
    })
    const loginData = loginRes.data || {}
    if (loginData.qrcode) {
      qrImageUrl.value = loginData.qrcode.startsWith('data:') ? loginData.qrcode : `data:image/png;base64,${loginData.qrcode}`
    } else if (loginData.qr_url) {
      qrImageUrl.value = loginData.qr_url
    } else {
      qrError.value = '未获取到登录二维码'
      qrLoading.value = false
      startingInstance.value = false
      return
    }

    qrLoading.value = false
    startingInstance.value = false
    startQrAutoRefresh()
  } catch (e) {
    qrError.value = e?.response?.data?.message || e.message || '启动企业微信失败'
    qrLoading.value = false
    startingInstance.value = false
  }
}

async function fetchLoginWindowScreenshot(inst) {
  if (!inst) return
  const runtimeKey = getInstanceRuntimeKey(inst)
  currentLoginInstanceKey.value = runtimeKey
  currentLoginInstance.value = inst
  screenshotLoading.value = true
  qrDialogVisible.value = true
  resetLoginDialogState()
  qrDisplayMode.value = 'screenshot'
  qrLoading.value = true
  clearQrTimers()

  try {
    const res = await proxyLoginWindowScreenshot({
      api_base_url: apiBaseUrl.value,
      api_key: configForm.apiKey || null,
      pid: inst.pid || null,
      wxid: inst.wxid || null,
      client_id: inst.client_id || null
    })
    const data = res.data || {}
    if (!data.image) {
      qrError.value = '未获取到窗口截图'
      return
    }
    qrDisplayMode.value = 'screenshot'
    qrImageUrl.value = data.image
    screenshotPid.value = data.pid || inst.pid || null
  } catch (error) {
    qrError.value = error?.response?.data?.message || error.message || '获取登录窗口截图失败'
  } finally {
    qrLoading.value = false
    screenshotLoading.value = false
  }
}

async function handleLoginInstance(inst) {
  if (!apiBaseUrl.value) {
    ElMessage.warning('请先配置 API 连接信息')
    return
  }
  if (!canShowLoginButton(inst)) {
    ElMessage.warning('当前实例不是可登录状态')
    return
  }
  await fetchLoginWindowScreenshot(inst)
}

async function handleRefreshLoginScreenshot() {
  if (!currentLoginInstance.value) return
  await fetchLoginWindowScreenshot(currentLoginInstance.value)
}

async function handleManualRefreshQr() {
  qrRefreshing.value = true
  await doRefreshQr()
  startQrAutoRefresh()
  qrRefreshing.value = false
}

function handleRetryQr() {
  if (qrDisplayMode.value === 'screenshot' && currentLoginInstance.value) {
    handleRefreshLoginScreenshot()
    return
  }
  handleAddInstance()
}

function handleQrDialogClosed() {
  clearQrTimers()
  resetLoginDialogState()
  currentLoginInstanceKey.value = ''
  currentLoginInstance.value = null
  handleFetchInstances()
}

onBeforeUnmount(() => {
  clearQrTimers()
})

onMounted(async () => {
  await loadConfig()
  if (hasApiConfig.value) {
    handleFetchInstances()
  }
})
</script>

<style scoped>
.lark-wechat-config {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* 每个配置区域为独立卡片 */
.config-section {
  background: var(--lark-bg-body, #f7f8fa);
  border-radius: 10px;
  padding: 24px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: var(--lark-text-primary);
  margin-bottom: 20px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--lark-border-light, #eee);
}

.section-title .el-icon {
  font-size: 18px;
  color: var(--lark-primary, #3370ff);
}

.config-form {
  max-width: 560px;
}

.form-row {
  display: flex;
  gap: 12px;
}

.form-col { flex: 1; }
.form-col-sm { width: 120px; flex-shrink: 0; }

.form-actions {
  display: flex;
  gap: 12px;
  margin-top: 4px;
}

/* 测试结果 */
.test-result {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 16px;
  border-radius: 8px;
  margin-top: 16px;
  max-width: 560px;
}

.test-result.success {
  background-color: #e8f8ef;
  color: #00B365;
}

.test-result.error {
  background-color: #fef0f0;
  color: #f54a45;
}

.test-result .el-icon { font-size: 18px; margin-top: 1px; }

.test-title {
  font-weight: 600;
  font-size: 14px;
  margin-bottom: 2px;
}

.test-detail {
  font-size: 13px;
  opacity: 0.85;
}

/* 实例列表 */
.instance-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.instance-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  background: var(--lark-bg-base, #fff);
  border: 1.5px solid transparent;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}

.instance-item:hover {
  border-color: var(--lark-primary);
  box-shadow: 0 2px 8px rgba(51,112,255,0.08);
}

.instance-item.selected {
  border-color: var(--lark-primary);
  background: linear-gradient(135deg, rgba(51,112,255,0.04), rgba(51,112,255,0.08));
}

.instance-item.disabled {
  opacity: 0.7;
}

.inst-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.inst-avatar {
  width: 42px;
  height: 42px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.inst-avatar.online {
  background: linear-gradient(135deg, #d4f5e2, #e8f8ef);
  color: #00B365;
}

.inst-avatar.offline {
  background-color: #f5f5f5;
  color: var(--lark-text-disabled);
}

.inst-avatar.pending {
  background: linear-gradient(135deg, #fff0d6, #fff7e8);
  color: #ff8800;
}

.inst-avatar-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 10px;
}

.inst-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--lark-text-primary);
  margin-bottom: 2px;
}

.inst-wxid {
  font-size: 12px;
  color: var(--lark-text-secondary);
  font-family: 'SF Mono', 'Menlo', monospace;
}

.inst-meta {
  font-size: 12px;
  color: var(--lark-text-secondary);
  margin-bottom: 2px;
}

.inst-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.inst-status-group {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.inst-status {
  font-size: 11px;
  font-weight: 500;
  padding: 3px 10px;
  border-radius: 12px;
}

.inst-status.online {
  background-color: #e8f8ef;
  color: #00B365;
}

.inst-status.offline {
  background-color: #f5f5f5;
  color: var(--lark-text-disabled);
}

.inst-disabled-text {
  font-size: 12px;
  color: var(--lark-text-secondary);
}

.instance-summary {
  display: flex;
  gap: 12px;
  margin-top: 18px;
  flex-wrap: wrap;
}

.summary-item {
  min-width: 100px;
  padding: 12px 16px;
  border-radius: 10px;
  background: var(--lark-bg-base, #fff);
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}

.summary-label {
  display: block;
  font-size: 12px;
  color: var(--lark-text-secondary);
  margin-bottom: 6px;
}

.summary-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--lark-text-primary);
}

.summary-value.success {
  color: #00B365;
}

.auto-receive-tip {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-top: 16px;
  padding: 14px 16px;
  border-radius: 8px;
  background: var(--lark-bg-base, #fff);
}

.auto-receive-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.auto-receive-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--lark-text-primary);
}

.auto-receive-text {
  font-size: 13px;
  color: var(--lark-text-secondary);
  line-height: 1.6;
}

.compat-address-panel {
  margin-top: 16px;
  padding: 16px;
  border: 1px dashed var(--lark-border-light);
  border-radius: 8px;
  background: var(--lark-bg-base, #fff);
}

.compat-address-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--lark-text-primary);
}

.compat-address-desc {
  margin-top: 6px;
  margin-bottom: 12px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--lark-text-secondary);
}

.compat-address-form {
  max-width: 820px;
}

.empty-hint {
  padding: 40px;
  text-align: center;
  color: var(--lark-text-secondary);
  font-size: 14px;
}

.bound-info {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 16px;
  padding: 12px 16px;
  background: linear-gradient(135deg, rgba(51,112,255,0.06), rgba(51,112,255,0.1));
  border-radius: 8px;
  font-size: 13px;
  color: var(--lark-primary);
}

:deep(.el-form-item__label) {
  padding-bottom: 4px;
  font-weight: 500;
  font-size: 13px;
  color: var(--lark-text-primary);
}

.qr-dialog-body {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-height: 320px;
  justify-content: center;
}

.qr-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 280px;
  font-size: 14px;
  color: var(--lark-text-secondary);
}

.qr-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.qr-error-text {
  font-size: 14px;
  color: var(--el-color-danger);
  text-align: center;
}

.qr-code-wrapper {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.qr-code-image {
  width: 260px;
  height: 260px;
  border: 1px solid #eee;
  border-radius: 8px;
  object-fit: contain;
}

.qr-hint {
  font-size: 14px;
  color: var(--lark-text-primary);
  font-weight: 500;
}

.qr-countdown {
  font-size: 12px;
  color: var(--lark-text-secondary);
}
</style>
