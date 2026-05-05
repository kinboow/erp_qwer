<template>
  <div class="lark-ai-config">
    <div class="config-card">
      <div class="card-title">
        <el-icon><Cpu /></el-icon>
        <span>AI 模型连接</span>
      </div>

      <el-form :model="form" label-position="top" class="config-form">
        <el-form-item label="模型供应商">
          <el-radio-group v-model="form.ai_provider" @change="onProviderChange">
            <el-radio-button v-for="(preset, key) in providers" :key="key" :value="key">
              {{ preset.label }}
            </el-radio-button>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="API 基地址" v-if="form.ai_provider === 'custom'">
          <el-input v-model="form.ai_base_url" placeholder="输入 OpenAI 兼容的 API 基地址" />
        </el-form-item>
        <el-form-item label="API 基地址" v-else>
          <el-input :model-value="currentPresetUrl" disabled />
          <div class="form-hint">由供应商预设，切换供应商可自动更新</div>
        </el-form-item>

        <el-form-item label="API Key">
          <el-input v-model="form.ai_api_key" :placeholder="maskedApiKey || apiKeyPlaceholder" show-password />
        </el-form-item>

        <div class="form-row">
          <el-form-item label="默认模型" class="form-col">
            <el-input v-model="form.ai_model" :placeholder="modelPlaceholder" />
          </el-form-item>
          <el-form-item label="多模态模型" class="form-col">
            <el-input v-model="form.ai_vision_model" :placeholder="visionModelPlaceholder || '默认同上'" />
          </el-form-item>
        </div>
      </el-form>
    </div>

    <div class="config-card">
      <div class="card-title">
        <el-icon><Setting /></el-icon>
        <span>解析参数</span>
      </div>

      <div class="sync-strategy-grid">
        <div class="strategy-item">
          <div class="strategy-label">生成温度</div>
          <el-input-number v-model="temperature" :min="0" :max="1" :step="0.1" :precision="1" controls-position="right" />
        </div>
        <div class="strategy-item">
          <div class="strategy-label">启用 AI 解析</div>
          <el-switch v-model="aiEnabled" active-text="开启" inactive-text="关闭" />
        </div>
      </div>

      <div class="form-actions">
        <el-button type="primary" @click="handleTest" :loading="testing" :disabled="!effectiveBaseUrl || (!form.ai_api_key && !maskedApiKey)">
          <el-icon><Connection /></el-icon>
          测试连接
        </el-button>
        <el-button type="success" @click="handleSave" :loading="saving" :disabled="!connectionTested">
          <el-icon><Check /></el-icon>
          保存配置
        </el-button>
      </div>
    </div>

    <!-- 熔断器状态卡片 -->
    <div class="config-card" :class="{ 'card-error': cbStatus.tripped }">
      <div class="card-title">
        <el-icon><Warning /></el-icon>
        <span>AI 服务状态</span>
        <el-tag v-if="cbStatus.tripped" type="danger" size="small" style="margin-left:auto">已暂停</el-tag>
        <el-tag v-else type="success" size="small" style="margin-left:auto">正常</el-tag>
      </div>

      <template v-if="cbStatus.tripped">
        <el-alert
          type="error"
          :closable="false"
          show-icon
          style="margin-bottom:16px"
        >
          <template #title>
            AI 连续 {{ cbStatus.consecutive_errors }} 次调用失败，已自动暂停
          </template>
          <template #default>
            <div style="margin-top:4px">错误：{{ cbStatus.last_error }}</div>
            <div style="margin-top:2px;color:#909399;font-size:12px">暂停于 {{ cbStatus.tripped_at }}</div>
            <div style="margin-top:2px;color:#909399;font-size:12px">期间缓冲了 {{ cbStatus.buffered_message_count || 0 }} 条客户消息</div>
          </template>
        </el-alert>

        <div class="form-actions">
          <el-button type="primary" @click="handleRecover" :loading="recovering">
            <el-icon><RefreshRight /></el-icon>
            我已恢复
          </el-button>
        </div>
      </template>

      <template v-else>
        <div style="color:#67c23a;font-size:13px;display:flex;align-items:center;gap:6px">
          <el-icon><CircleCheck /></el-icon>
          AI 服务运行正常
          <span v-if="cbStatus.last_error_at" style="color:#909399;margin-left:12px;font-size:12px">
            最近错误：{{ cbStatus.last_error_at }}
          </span>
        </div>
        <div class="form-actions" style="margin-top:12px">
          <el-button type="primary" disabled plain>
            <el-icon><RefreshRight /></el-icon>
            我已恢复
          </el-button>
        </div>
      </template>
    </div>

    <!-- 缓冲消息选择对话框 -->
    <el-dialog v-model="reprocessDialogVisible" title="选择需要重新处理的消息" width="680px">
      <el-alert type="info" :closable="false" style="margin-bottom:12px">
        AI 已恢复正常，以下是暂停期间收到的消息。请勾选需要重新交给 AI 处理的项目。
        发货扫码类消息会自动检查纸张ID是否已识别过，避免重复下单。
      </el-alert>
      <el-table :data="bufferedMessages" @selection-change="onBufferedSelectionChange" max-height="400" border>
        <el-table-column type="selection" width="45" />
        <el-table-column label="类型" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.message_type === 'shipping_scan'" type="warning" size="small">发货扫码</el-tag>
            <el-tag v-else type="primary" size="small">客户群</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="客户/订单" width="130">
          <template #default="{ row }">{{ row.order_no || row.customer_name || '-' }}</template>
        </el-table-column>
        <el-table-column label="发送人" prop="sender_name" width="90" />
        <el-table-column label="内容" prop="content_preview" min-width="180" show-overflow-tooltip />
        <el-table-column label="时间" width="150">
          <template #default="{ row }">{{ row.created_at?.replace('T', ' ')?.slice(0, 19) || '-' }}</template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="handleSkipReprocess">跳过（不处理）</el-button>
        <el-button type="primary" @click="handleReprocess" :loading="reprocessing" :disabled="!hasSelectedItems">
          处理选中 ({{ selectedCount }} 项)
        </el-button>
      </template>
    </el-dialog>

  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Cpu, Setting, Connection, Check, Warning, RefreshRight, CircleCheck } from '@element-plus/icons-vue'
import {
  getAiConfig, getAiProviders, saveAiConfig, testAiConnection,
  getAiCircuitBreakerStatus, getAiBufferedMessages, recoverAi, reprocessAiMessages
} from '@/api/aiConfig'

const saving = ref(false)
const testing = ref(false)
const connectionTested = ref(false)

const providers = ref({
  qwen: { label: '通义千问（阿里云）', base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', default_model: 'qwen3.5-flash', default_vision_model: 'qwen3.5-flash' },
  bytedance: { label: '豆包（字节跳动 · 火山方舟）', base_url: 'https://ark.cn-beijing.volces.com/api/v3', default_model: 'doubao-seed-2-0-lite-260215', default_vision_model: 'doubao-seed-2-0-lite-260215' },
  custom: { label: '自定义（OpenAI 兼容）', base_url: '', default_model: '', default_vision_model: '' },
})

const form = reactive({
  ai_provider: 'qwen',
  ai_base_url: '',
  ai_api_key: '',
  ai_model: '',
  ai_vision_model: '',
})

const temperature = ref(0.1)
const aiEnabled = ref(true)
const maskedApiKey = ref('')

const currentPreset = computed(() => providers.value[form.ai_provider] || {})
const currentPresetUrl = computed(() => currentPreset.value.base_url || '')
const effectiveBaseUrl = computed(() => form.ai_provider === 'custom' ? form.ai_base_url : currentPresetUrl.value)
const modelPlaceholder = computed(() => currentPreset.value.default_model ? `如：${currentPreset.value.default_model}` : '输入模型名称')
const visionModelPlaceholder = computed(() => currentPreset.value.default_vision_model ? `如：${currentPreset.value.default_vision_model}` : '')
const apiKeyPlaceholder = computed(() => {
  const p = form.ai_provider
  if (p === 'qwen') return '请输入通义千问 API Key'
  if (p === 'bytedance') return '请输入火山方舟 API Key'
  return '请输入 API Key'
})

function onProviderChange(provider) {
  const preset = providers.value[provider]
  if (!preset) return
  if (provider !== 'custom') {
    form.ai_base_url = preset.base_url
  }
  // 切换供应商时清空模型名，让用户根据提示填写
  form.ai_model = ''
  form.ai_vision_model = ''
  maskedApiKey.value = ''
  form.ai_api_key = ''
  connectionTested.value = false
}

async function loadProviders() {
  try {
    const res = await getAiProviders()
    if (res.data) providers.value = res.data
  } catch { /* use defaults */ }
}

async function loadConfig() {
  try {
    const res = await getAiConfig()
    const cfg = res.data || {}
    form.ai_provider = cfg.ai_provider || 'qwen'
    form.ai_base_url = cfg.ai_base_url || ''
    maskedApiKey.value = cfg.ai_api_key || ''
    form.ai_api_key = ''
    form.ai_model = cfg.ai_model || ''
    form.ai_vision_model = cfg.ai_vision_model || ''
    temperature.value = parseFloat(cfg.ai_temperature) || 0.1
    aiEnabled.value = cfg.ai_enabled !== false
  } catch { /* first load */ }
}

async function handleSave() {
  if (!connectionTested.value) {
    ElMessage.warning('请先测试连接成功后再保存配置')
    return
  }
  saving.value = true
  try {
    const payload = {
      ai_provider: form.ai_provider,
      ai_base_url: effectiveBaseUrl.value,
      ai_model: form.ai_model,
      ai_vision_model: form.ai_vision_model,
      ai_temperature: String(temperature.value),
      ai_enabled: aiEnabled.value ? 'true' : 'false',
    }
    if (form.ai_api_key) {
      payload.ai_api_key = form.ai_api_key
    }
    const enteredKey = form.ai_api_key
    await saveAiConfig(payload)
    ElMessage.success('AI 配置已保存')
    await loadConfig()
    if (enteredKey) {
      form.ai_api_key = enteredKey
    }
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function handleTest() {
  testing.value = true
  try {
    const testPayload = {
      ai_base_url: effectiveBaseUrl.value,
      ai_model: form.ai_model,
    }
    if (form.ai_api_key) {
      testPayload.ai_api_key = form.ai_api_key
    }
    const res = await testAiConnection(testPayload)
    connectionTested.value = true
    ElMessage.success('AI 连接测试成功')
  } catch (e) {
    connectionTested.value = false
    const msg = e?.message || e?.response?.data?.message || '连接测试失败'
    ElMessage.error(msg)
  } finally {
    testing.value = false
  }
}

// ---------------------------------------------------------------------------
// AI 熔断器
// ---------------------------------------------------------------------------
const cbStatus = ref({ tripped: false, consecutive_errors: 0 })
const recovering = ref(false)
const reprocessDialogVisible = ref(false)
const bufferedMessages = ref([])
const selectedItems = ref([])
const reprocessing = ref(false)
const selectedRoomIds = computed(() => {
  const ids = new Set()
  selectedItems.value.filter(r => r.message_type !== 'shipping_scan' && r.room_id).forEach(r => ids.add(r.room_id))
  return [...ids]
})
const selectedShippingRecordIds = computed(() => {
  return selectedItems.value.filter(r => r.message_type === 'shipping_scan' && r.record_id).map(r => r.record_id)
})
const hasSelectedItems = computed(() => selectedRoomIds.value.length > 0 || selectedShippingRecordIds.value.length > 0)
const selectedCount = computed(() => selectedRoomIds.value.length + selectedShippingRecordIds.value.length)
let cbPollTimer = null

async function loadCbStatus() {
  try {
    const res = await getAiCircuitBreakerStatus()
    cbStatus.value = res.data || { tripped: false }
  } catch { /* ignore */ }
}

async function handleRecover() {
  recovering.value = true
  try {
    const res = await recoverAi()
    if (res.code === 200) {
      ElMessage.success('AI 测试通过，已恢复正常')
      await loadCbStatus()
      // 有缓冲消息则弹出选择对话框
      if ((res.data?.buffered_count || 0) > 0) {
        const msgRes = await getAiBufferedMessages()
        bufferedMessages.value = msgRes.data || []
        if (bufferedMessages.value.length > 0) {
          reprocessDialogVisible.value = true
        }
      }
    } else {
      ElMessage.error(res.message || 'AI 恢复失败，请检查配置')
    }
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || e?.message || 'AI 恢复失败')
  } finally {
    recovering.value = false
  }
}

function onBufferedSelectionChange(rows) {
  selectedItems.value = rows
}

function handleSkipReprocess() {
  reprocessDialogVisible.value = false
  bufferedMessages.value = []
  selectedItems.value = []
}

async function handleReprocess() {
  if (!hasSelectedItems.value) return
  reprocessing.value = true
  try {
    const res = await reprocessAiMessages({
      room_ids: selectedRoomIds.value,
      shipping_record_ids: selectedShippingRecordIds.value,
    })
    const d = res.data || {}
    const okRooms = (d.processed_rooms || []).length
    const okScans = (d.processed_scans || []).length
    const errCount = (d.errors || []).length
    let msg = ''
    if (okRooms) msg += `${okRooms} 个客户群`
    if (okScans) msg += `${msg ? '、' : ''}${okScans} 个发货扫码`
    if (errCount) msg += `，${errCount} 项失败`
    ElMessage.success(`已处理 ${msg || '0 项'}`)
    reprocessDialogVisible.value = false
    bufferedMessages.value = []
    selectedItems.value = []
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || '重处理失败')
  } finally {
    reprocessing.value = false
  }
}

onMounted(async () => {
  await loadProviders()
  await loadConfig()
  await loadCbStatus()
  cbPollTimer = setInterval(loadCbStatus, 10000)
})

onUnmounted(() => {
  if (cbPollTimer) clearInterval(cbPollTimer)
})

watch(
  () => [form.ai_base_url, form.ai_api_key, form.ai_model, form.ai_provider],
  () => {
    connectionTested.value = false
  }
)
</script>

<style scoped>
.lark-ai-config {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

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

.config-form {
  max-width: 640px;
}

.form-hint {
  font-size: 12px;
  color: var(--lark-text-tertiary, #a8abb2);
  margin-top: 4px;
  line-height: 1.4;
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

.sync-strategy-grid {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 20px;
}

.strategy-item {
  background: var(--lark-bg-base, #fff);
  border-radius: 10px;
  padding: 16px 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  min-width: 160px;
}

.strategy-label {
  font-size: 12px;
  color: var(--lark-text-secondary, #8f959e);
  margin-bottom: 10px;
  font-weight: 500;
}

.form-actions {
  display: flex;
  gap: 12px;
}

.card-error {
  border: 1.5px solid #f56c6c;
  background: #fef0f0 !important;
}

</style>
