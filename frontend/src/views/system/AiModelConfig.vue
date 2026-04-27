<template>
  <div class="lark-ai-config">
    <div class="config-card">
      <div class="card-title">
        <el-icon><Cpu /></el-icon>
        <span>AI 模型连接</span>
      </div>

      <el-form :model="form" label-position="top" class="config-form">
        <el-form-item label="API 基地址">
          <el-input v-model="form.ai_base_url" placeholder="如：https://open.bigmodel.cn/api/paas/v4" />
        </el-form-item>

        <el-form-item label="API Key">
          <el-input v-model="form.ai_api_key" :placeholder="maskedApiKey || '请输入智谱 API Key'" show-password />
        </el-form-item>

        <div class="form-row">
          <el-form-item label="默认模型" class="form-col">
            <el-input v-model="form.ai_model" placeholder="如：GLM-4.6V" />
          </el-form-item>
          <el-form-item label="多模态模型" class="form-col">
            <el-input v-model="form.ai_vision_model" placeholder="默认同上" />
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
        <el-button type="primary" @click="handleTest" :loading="testing" :disabled="!form.ai_base_url || (!form.ai_api_key && !maskedApiKey)">
          <el-icon><Connection /></el-icon>
          测试连接
        </el-button>
        <el-button type="success" @click="handleSave" :loading="saving">
          <el-icon><Check /></el-icon>
          保存配置
        </el-button>
      </div>
    </div>

    <div v-if="testResult" class="config-card">
      <div class="card-title">
        <el-icon><DataAnalysis /></el-icon>
        <span>测试结果</span>
      </div>
      <div class="test-result">
        <div class="test-item">
          <span class="test-label">模型</span>
          <span class="test-value">{{ testResult.model }}</span>
        </div>
        <div class="test-item">
          <span class="test-label">回复</span>
          <span class="test-value">{{ testResult.reply }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Cpu, Setting, Connection, Check, DataAnalysis } from '@element-plus/icons-vue'
import { getAiConfig, saveAiConfig, testAiConnection } from '@/api/aiConfig'

const saving = ref(false)
const testing = ref(false)
const testResult = ref(null)

const form = reactive({
  ai_base_url: '',
  ai_api_key: '',
  ai_model: '',
  ai_vision_model: '',
})

const temperature = ref(0.1)
const aiEnabled = ref(true)
const maskedApiKey = ref('')

async function loadConfig() {
  try {
    const res = await getAiConfig()
    const cfg = res.data || {}
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
  saving.value = true
  try {
    const payload = {
      ai_base_url: form.ai_base_url,
      ai_model: form.ai_model,
      ai_vision_model: form.ai_vision_model,
      ai_temperature: String(temperature.value),
      ai_enabled: aiEnabled.value ? 'true' : 'false',
    }
    if (form.ai_api_key) {
      payload.ai_api_key = form.ai_api_key
    }
    await saveAiConfig(payload)
    ElMessage.success('AI 配置已保存')
    await loadConfig()
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function handleTest() {
  testing.value = true
  testResult.value = null
  try {
    const testPayload = {
      ai_base_url: form.ai_base_url,
      ai_model: form.ai_model,
    }
    if (form.ai_api_key) {
      testPayload.ai_api_key = form.ai_api_key
    }
    const res = await testAiConnection(testPayload)
    testResult.value = res.data || {}
    ElMessage.success('AI 连接测试成功')
  } catch (e) {
    const msg = e?.message || e?.response?.data?.message || '连接测试失败'
    ElMessage.error(msg)
  } finally {
    testing.value = false
  }
}

onMounted(loadConfig)
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

.test-result {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.test-item {
  display: flex;
  align-items: center;
  gap: 12px;
}

.test-label {
  font-size: 13px;
  color: var(--lark-text-secondary, #8f959e);
  min-width: 50px;
  font-weight: 500;
}

.test-value {
  font-size: 14px;
  color: var(--lark-text-primary, #1f2329);
}
</style>
