<template>
  <div class="lark-printer-config">
    <div class="config-section">
      <div class="section-title">
        <el-icon><Monitor /></el-icon>
        <span>远程打印机</span>
      </div>

      <div class="row-item">
        <div class="label">选择客户端</div>
        <el-select v-model="selectedClient" filterable placeholder="请选择客户端" @change="onClientChange" style="width: 100%" :loading="loadingClients" loading-text="加载中...">
          <el-option
            v-for="c in clients"
            :key="c.hostname"
            :label="`${c.hostname}${c.online ? ' (在线)' : ' (离线)'}`"
            :value="c.hostname"
          />
        </el-select>
      </div>

      <div v-if="currentPrinter" class="row-item">
        <div class="label">当前打印机</div>
        <div class="printer-info">{{ currentPrinter }}</div>
      </div>

      <div class="form-actions">
        <el-button type="primary" :icon="Printer" @click="handleTestPrint" :loading="testing">测试打印</el-button>
        <el-button type="success" :icon="Check" @click="handleSave" :loading="saving" :disabled="!printTested">保存配置</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Monitor, Refresh, Printer, Check } from '@element-plus/icons-vue'
import { getPrinterClients, getPrinterConfig, savePrinterConfig, sendTestPrint } from '@/api/printer'

const loadingClients = ref(false)
const testing = ref(false)
const saving = ref(false)
const printTested = ref(false)
const clients = ref([])
const selectedClient = ref('')
let pollTimer = null

const currentPrinter = computed(() => {
  const c = clients.value.find(x => x.hostname === selectedClient.value)
  return c?.printer_name || ''
})

async function saveTargetConfig() {
  await savePrinterConfig({
    printer_target_client: selectedClient.value || '',
  })
}

async function loadConfig() {
  try {
    const res = await getPrinterConfig()
    const cfg = res.data || {}
    selectedClient.value = cfg.printer_target_client || ''
  } catch {}
}

async function loadClients() {
  loadingClients.value = true
  try {
    const res = await getPrinterClients()
    clients.value = res.data || []
    if (!selectedClient.value && clients.value.length > 0) {
      selectedClient.value = clients.value[0].hostname
    }
  } catch (e) {
    clients.value = []
    ElMessage.error(e?.response?.data?.message || '加载客户端失败')
  } finally {
    loadingClients.value = false
  }
}

async function onClientChange() {
  printTested.value = false
}

async function handleTestPrint() {
  if (!selectedClient.value) {
    ElMessage.warning('请先选择客户端')
    return
  }
  testing.value = true
  try {
    await sendTestPrint(selectedClient.value, '')
    printTested.value = true
    ElMessage.success('测试打印任务已发送')
  } catch (e) {
    printTested.value = false
    ElMessage.error(e?.response?.data?.message || '测试打印失败')
  } finally {
    testing.value = false
  }
}

async function handleSave() {
  if (!printTested.value) {
    ElMessage.warning('请先测试打印成功后再保存配置')
    return
  }
  saving.value = true
  try {
    await saveTargetConfig()
    ElMessage.success('配置已保存')
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function pollClients() {
  try {
    const res = await getPrinterClients()
    const newList = res.data || []
    const oldMap = Object.fromEntries(clients.value.map(c => [c.hostname, c.online]))
    for (const c of newList) {
      const was = oldMap[c.hostname]
      if (was === undefined && c.online) {
        ElMessage.success(`客户端 ${c.hostname} 已上线`)
      } else if (was === true && !c.online) {
        ElMessage.warning(`客户端 ${c.hostname} 已离线`)
      } else if (was === false && c.online) {
        ElMessage.success(`客户端 ${c.hostname} 已上线`)
      }
    }
    clients.value = newList
    if (!selectedClient.value && newList.length > 0) {
      selectedClient.value = newList[0].hostname
    }
  } catch {}
}

onMounted(async () => {
  loadingClients.value = true
  await loadConfig()
  await loadClients()
  pollTimer = setInterval(pollClients, 5000)
})

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.lark-printer-config {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.config-section {
  background: var(--lark-bg-base, #fff);
  border-radius: var(--lark-radius-lg, 8px);
  padding: 20px 24px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: var(--lark-text-primary, #1f2329);
  margin-bottom: 16px;
}

.row-item {
  margin-bottom: 14px;
}

.label {
  margin-bottom: 8px;
  font-size: 13px;
  color: var(--lark-text-secondary, #646a73);
}

.printer-info {
  padding: 8px 12px;
  background: var(--lark-bg-body, #f5f6f7);
  border-radius: 6px;
  font-size: 13px;
  color: var(--lark-text-primary, #1f2329);
}

.form-actions {
  display: flex;
  gap: 12px;
  margin-top: 16px;
}
</style>
