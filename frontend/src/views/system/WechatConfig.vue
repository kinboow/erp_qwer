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


      <!-- 已绑定实例信息 -->
      <div v-if="boundInstanceInfo" class="bound-info">
        <el-icon color="var(--lark-primary)"><InfoFilled /></el-icon>
        <span>当前绑定实例：<strong>{{ boundInstanceInfo.nickname || boundInstanceInfo.wxid }}</strong></span>
      </div>


    </div>

    <!-- 登录提示弹窗 -->
    <el-dialog
      v-model="loginPromptVisible"
      title="请登录企业微信"
      width="420px"
      :close-on-click-modal="false"
      align-center
    >
      <div class="login-prompt-body">
        <el-icon :size="48" color="var(--lark-primary)"><Monitor /></el-icon>
        <div class="login-prompt-text">
          企业微信实例已启动，请在<strong>客户端窗口</strong>中完成登录操作。<br/>
          登录完成后点击下方按钮确认。
        </div>
      </div>
      <template #footer>
        <el-button @click="handleCancelLogin">取消</el-button>
        <el-button type="primary" @click="handleConfirmLoggedIn" :loading="loginPromptChecking">我已登录</el-button>
      </template>
    </el-dialog>

  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Connection, Check, Refresh, Monitor, User, Select,
  InfoFilled, Plus
} from '@element-plus/icons-vue'
import { getInstances, createInstance, updateInstance, getWechatGlobalConfig, saveWechatGlobalConfig, proxyStartWechat } from '@/api/wechat'
import request from '@/utils/request'

const formRef = ref(null)
const testing = ref(false)
const saving = ref(false)
const fetchingInstances = ref(false)
const connectionTested = ref(false)
const testResult = ref(null)
const instances = ref([])
const selectedWxid = ref('')

const startingInstance = ref(false)
const loginPromptVisible = ref(false)
const loginPromptChecking = ref(false)
const pendingLoginInst = ref(null)

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
const boundInstanceInfo = computed(() => {
  if (!selectedWxid.value) return null
  return instances.value.find(i => i.wxid === selectedWxid.value) || { wxid: selectedWxid.value, nickname: '' }
})

watch(
  () => [configForm.host, configForm.port, configForm.apiKey],
  (newVal, oldVal) => {
    if (!configLoaded.value || !oldVal) return
    if (newVal[0] !== oldVal[0] || newVal[1] !== oldVal[1] || newVal[2] !== oldVal[2]) {
      connectionTested.value = false
      testResult.value = null
    }
  }
)

const getInstanceStatusClass = (inst) => {
  if (inst.login_status) return 'online'
  if (inst.status || inst.attached) return 'pending'
  return 'offline'
}

const canShowLoginButton = (inst) => !!inst?.status && !inst?.login_status && !!(inst?.pid || inst?.client_id || inst?.wxid)

async function loadConfig() {
  try {
    const res = await getWechatGlobalConfig()
    const cfg = res.data || {}
    configForm.host = cfg.host || ''
    configForm.port = cfg.port || ''
    configForm.apiKey = cfg.api_key || ''
    selectedWxid.value = cfg.selected_wxid || ''
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

async function ensureInstanceRecord(inst) {
  const wxid = (inst?.wxid || selectedWxid.value || '').trim()
  if (!wxid) return
  const existing = await getInstances()
  const list = Array.isArray(existing.data) ? existing.data : []
  const found = list.find(i => i.wxid === wxid)
  const payload = {
    wxid,
    name: inst?.nickname || inst?.name || found?.name || wxid,
    api_base_url: apiBaseUrl.value,
    api_key: configForm.apiKey || null
  }
  if (found?.id) {
    await updateInstance(found.id, {
      name: payload.name,
      api_base_url: payload.api_base_url,
      api_key: payload.api_key
    })
  } else {
    await createInstance(payload)
  }
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

      testResult.value = null
      ElMessage.success(`连接测试成功：API 服务正常 (${apiBaseUrl.value})`)
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
    if (selectedWxid.value) {
      const inst = instances.value.find(i => i.wxid === selectedWxid.value)
      await ensureInstanceRecord(inst)
    }

    await saveConfigToDb()

    ElMessage.success('配置已保存，消息接收已自动开启')
    handleFetchInstances()
  } catch (error) {
    ElMessage.error(error?.response?.data?.message || error?.message || '保存失败')
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
    // 仅在用户从未选择过实例时自动选中，不覆盖已保存的选择
    if (instances.value.length > 0 && !selectedWxid.value) {
      const attached = instances.value.find(i => i.login_status && i.wxid) || instances.value.find(i => i.attached && i.wxid) || instances.value.find(i => i.wxid)
      if (attached) {
        selectedWxid.value = attached.wxid
        ensureInstanceRecord(attached).catch(() => {})
        saveConfigToDb().catch(() => {})
      }
    }
    if (selectedWxid.value) {
      const current = instances.value.find(i => i.wxid === selectedWxid.value)
      if (current) {
        ensureInstanceRecord(current).catch(() => {})
      }
    }
  } catch (error) {
    ElMessage.warning('获取实例列表失败，使用上次保存的配置')
    // 不清空 instances，保留已绑定的实例信息可见
  } finally {
    fetchingInstances.value = false
  }
}

async function handleSelectInstance(inst) {
  if (!inst.wxid) {
    ElMessage.warning('该实例尚未登录，暂时无法绑定')
    return
  }
  selectedWxid.value = inst.wxid
  try {
    await ensureInstanceRecord(inst)
    await saveConfigToDb()
  } catch {
    saveConfigToDb().catch(() => {})
  }
}

async function handleAddInstance() {
  if (!apiBaseUrl.value) {
    ElMessage.warning('请先配置 API 连接信息')
    return
  }

  startingInstance.value = true

  try {
    // 1) 启动实例
    const startRes = await proxyStartWechat({
      api_base_url: apiBaseUrl.value,
      api_key: configForm.apiKey || null,
      force_new: true
    })
    const startData = startRes.data || {}
    const pid = startData.pid || null
    const wxid = startData.wxid || startData.client_id || ''

    if (!pid && !wxid) {
      ElMessage.error('启动成功但未返回实例标识')
      startingInstance.value = false
      return
    }

    // 2) 刷新实例列表，检查登录状态
    await handleFetchInstances()
    const newInst = instances.value.find(i =>
      (pid && i.pid === pid) || (wxid && i.wxid === wxid)
    )

    if (newInst && newInst.login_status) {
      // 已登录 → 不弹窗，直接提示
      ElMessage.success(`实例 ${newInst.nickname || newInst.wxid || pid} 已处于登录状态`)
      startingInstance.value = false
      return
    }

    // 3) 未登录 → 弹窗提示用户去客户端登录
    startingInstance.value = false
    pendingLoginInst.value = newInst || { pid, wxid, client_id: startData.client_id }
    loginPromptVisible.value = true
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || e.message || '启动企业微信失败')
    startingInstance.value = false
  }
}

async function handleConfirmLoggedIn() {
  loginPromptChecking.value = true
  try {
    await handleFetchInstances()
    const inst = pendingLoginInst.value
    if (!inst) return

    const found = instances.value.find(i =>
      (inst.pid && i.pid === inst.pid) || (inst.wxid && i.wxid === inst.wxid)
    )

    if (found && found.login_status) {
      // 确认已登录
      loginPromptVisible.value = false
      pendingLoginInst.value = null
      ElMessage.success(`实例 ${found.nickname || found.wxid} 登录成功`)
    } else {
      // 仍未登录 → 提示用户，保持弹窗
      ElMessage.warning('检测到实例尚未登录，请先在客户端完成登录后再点击确认')
    }
  } catch (e) {
    ElMessage.error('检查登录状态失败')
  } finally {
    loginPromptChecking.value = false
  }
}

async function handleCancelLogin() {
  const inst = pendingLoginInst.value
  const pid = inst?.pid
  loginPromptVisible.value = false
  pendingLoginInst.value = null

  if (pid) {
    try {
      await request({
        url: '/api/wechat/proxy/kill_process',
        method: 'post',
        data: { pid }
      })
      ElMessage.info(`已结束实例进程 (PID: ${pid})`)
    } catch (e) {
      ElMessage.warning('结束进程失败：' + (e?.response?.data?.message || e.message))
    }
  }
  handleFetchInstances()
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
  pendingLoginInst.value = inst
  loginPromptVisible.value = true
}

onMounted(async () => {
  await loadConfig()
  if (hasApiConfig.value) {
    await handleFetchInstances()
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

.login-prompt-body {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 20px 0;
  text-align: center;
}

.login-prompt-text {
  font-size: 14px;
  color: var(--lark-text-primary);
  line-height: 1.8;
}
</style>
