<template>
  <div class="lark-printer-config">
    <div class="config-section">
      <div class="section-title">
        <el-icon><Monitor /></el-icon>
        <span>远程打印机</span>
      </div>

      <div class="row-item">
        <div class="label">选择客户端</div>
        <el-select v-model="selectedClient" filterable placeholder="请选择客户端" @change="onClientChange" style="width: 100%">
          <el-option
            v-for="c in clients"
            :key="c.hostname"
            :label="`${c.hostname}${c.online ? ' (在线)' : ' (离线)'}`"
            :value="c.hostname"
          />
        </el-select>
      </div>

      <div class="row-item">
        <div class="label">选择打印机</div>
        <el-select v-model="selectedPrinter" filterable placeholder="请选择打印机" @change="onPrinterChange" style="width: 100%">
          <el-option v-for="p in printerOptions" :key="p" :label="p" :value="p" />
        </el-select>
      </div>

      <div class="actions">
        <el-button :icon="Refresh" @click="loadClients" :loading="loadingClients">刷新客户端</el-button>
        <el-button type="primary" :icon="Printer" @click="handleTestPrint" :loading="testing">测试打印</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Monitor, Refresh, Printer } from '@element-plus/icons-vue'
import { getPrinterClients, getPrinterConfig, savePrinterConfig, sendTestPrint } from '@/api/printer'

const loadingClients = ref(false)
const testing = ref(false)
const clients = ref([])
const selectedClient = ref('')
const selectedPrinter = ref('')

const printerOptions = computed(() => {
  const c = clients.value.find(x => x.hostname === selectedClient.value)
  return c?.printers || []
})

async function saveTargetConfig() {
  await savePrinterConfig({
    printer_target_client: selectedClient.value || '',
    printer_target_printer: selectedPrinter.value || '',
  })
}

async function loadConfig() {
  try {
    const res = await getPrinterConfig()
    const cfg = res.data || {}
    selectedClient.value = cfg.printer_target_client || ''
    selectedPrinter.value = cfg.printer_target_printer || ''
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
    if (!printerOptions.value.includes(selectedPrinter.value)) {
      selectedPrinter.value = printerOptions.value[0] || ''
    }
  } catch (e) {
    clients.value = []
    ElMessage.error(e?.response?.data?.message || '加载客户端失败')
  } finally {
    loadingClients.value = false
  }
}

async function onClientChange() {
  if (!printerOptions.value.includes(selectedPrinter.value)) {
    selectedPrinter.value = printerOptions.value[0] || ''
  }
  try {
    await saveTargetConfig()
  } catch {}
}

async function onPrinterChange() {
  try {
    await saveTargetConfig()
  } catch {}
}

async function handleTestPrint() {
  if (!selectedClient.value) {
    ElMessage.warning('请先选择客户端')
    return
  }
  if (!selectedPrinter.value) {
    ElMessage.warning('请先选择打印机')
    return
  }

  testing.value = true
  try {
    await saveTargetConfig()
    await sendTestPrint(selectedClient.value, selectedPrinter.value)
    ElMessage.success('测试打印任务已发送')
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || '测试打印失败')
  } finally {
    testing.value = false
  }
}

onMounted(async () => {
  await loadConfig()
  await loadClients()
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

.actions {
  display: flex;
  gap: 12px;
  margin-top: 10px;
}
</style>
