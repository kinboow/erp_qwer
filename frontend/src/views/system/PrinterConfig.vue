<template>
  <div class="lark-printer-config">
    <!-- 自动打印配置 -->
    <div class="config-section">
      <div class="section-title">
        <el-icon><Printer /></el-icon>
        <span>自动打印配置</span>
      </div>

      <div class="auto-print-row">
        <span class="auto-print-label">审核下单 / 替换旧单后自动将配货单加入打印队列</span>
        <el-switch v-model="autoPrint" active-text="开启" inactive-text="关闭" />
      </div>

      <div class="form-actions">
        <el-button type="success" @click="handleSave" :loading="saving">
          <el-icon><Check /></el-icon>
          保存配置
        </el-button>
      </div>

      <div v-if="configLoaded" class="saved-info">
        <el-icon color="var(--el-color-primary)"><InfoFilled /></el-icon>
        <span>当前状态：自动打印 <strong>{{ savedAutoPrint ? '已开启' : '已关闭' }}</strong></span>
      </div>
    </div>

    <!-- 打印客户端说明 -->
    <div class="config-section">
      <div class="section-title">
        <el-icon><Monitor /></el-icon>
        <span>打印客户端</span>
      </div>

      <div class="client-info">
        <div class="info-block">
          <div class="info-title">工作原理</div>
          <div class="info-desc">
            审核下单或替换旧单后，系统会自动生成配货单 PDF 并加入打印队列。
            独立运行的<strong>打印客户端</strong>会轮询服务器获取待打印任务，下载 PDF 后发送到本地打印机。
          </div>
        </div>

        <div class="info-block">
          <div class="info-title">使用步骤</div>
          <ol class="steps-list">
            <li>在需要连接打印机的电脑上运行 <code>print_client.py</code></li>
            <li>首次运行时配置服务器地址、登录账号和打印机</li>
            <li>配置保存在本地 <code>print_client_config.json</code>，下次自动加载</li>
            <li>客户端自动轮询服务器，有新任务时自动打印</li>
          </ol>
        </div>

        <div class="info-block">
          <div class="info-title">依赖安装</div>
          <div class="code-block">
            <code>pip install requests pywin32</code>
          </div>
          <div class="info-desc" style="margin-top: 6px;">
            推荐安装 <a href="https://www.sumatrapdfreader.org/download-free-pdf-viewer" target="_blank">SumatraPDF</a> 以获得最佳静默打印效果。
          </div>
        </div>
      </div>
    </div>

    <!-- 打印队列状态 -->
    <div class="config-section">
      <div class="section-title">
        <el-icon><List /></el-icon>
        <span>打印队列</span>
        <el-button size="small" :icon="Refresh" @click="loadQueue" :loading="loadingQueue" style="margin-left: auto;">
          刷新
        </el-button>
      </div>

      <div v-if="loadingQueue" v-loading="true" style="min-height: 60px;"></div>
      <div v-else-if="queueJobs.length === 0" class="empty-hint">当前无待打印任务</div>
      <el-table v-else :data="queueJobs" size="small" stripe>
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="order_no" label="订单号" width="160" />
        <el-table-column prop="doc_type" label="类型" width="90" align="center">
          <template #default="{ row }">
            <el-tag size="small">{{ row.doc_type === 'picking' ? '配货单' : row.doc_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.status === 'pending'" type="warning" size="small">待打印</el-tag>
            <el-tag v-else-if="row.status === 'done'" type="success" size="small">已完成</el-tag>
            <el-tag v-else type="danger" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="attempts" label="重试" width="60" align="center" />
        <el-table-column prop="error_msg" label="错误" min-width="150" show-overflow-tooltip />
        <el-table-column prop="created_at" label="创建时间" width="160" />
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Printer, Refresh, Check, Monitor, List, InfoFilled } from '@element-plus/icons-vue'
import { getPrinterConfig, savePrinterConfig } from '@/api/printer'
import request from '@/utils/request'

const saving = ref(false)
const autoPrint = ref(false)
const savedAutoPrint = ref(false)
const configLoaded = ref(false)
const loadingQueue = ref(false)
const queueJobs = ref([])

async function loadConfig() {
  try {
    const res = await getPrinterConfig()
    const cfg = res.data || {}
    autoPrint.value = cfg.printer_auto_print === 'true'
    savedAutoPrint.value = cfg.printer_auto_print === 'true'
    configLoaded.value = true
  } catch {}
}

async function handleSave() {
  saving.value = true
  try {
    await savePrinterConfig({
      printer_name: '',
      printer_auto_print: autoPrint.value ? 'true' : 'false',
    })
    savedAutoPrint.value = autoPrint.value
    ElMessage.success('配置已保存')
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function loadQueue() {
  loadingQueue.value = true
  try {
    const res = await request({ url: '/api/printer/queue/poll?limit=20', method: 'get' })
    queueJobs.value = res.data || []
  } catch { queueJobs.value = [] }
  finally { loadingQueue.value = false }
}

onMounted(async () => {
  await loadConfig()
  await loadQueue()
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

.empty-hint {
  padding: 20px;
  text-align: center;
  color: var(--lark-text-secondary, #646a73);
  font-size: 13px;
}

.auto-print-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
}

.auto-print-label {
  font-size: 14px;
  color: var(--lark-text-primary, #1f2329);
}

.form-actions {
  display: flex;
  gap: 12px;
  margin-top: 16px;
}

.saved-info {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 16px;
  padding: 10px 14px;
  background: var(--el-color-primary-light-9, #ecf5ff);
  border-radius: 6px;
  font-size: 13px;
  color: var(--lark-text-secondary, #646a73);
}

.client-info {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.info-block {
  padding: 0;
}

.info-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 6px;
  color: var(--lark-text-primary, #1f2329);
}

.info-desc {
  font-size: 13px;
  color: var(--lark-text-secondary, #646a73);
  line-height: 1.7;
}

.steps-list {
  padding-left: 20px;
  font-size: 13px;
  color: var(--lark-text-secondary, #646a73);
  line-height: 2;
}

.steps-list code {
  background: var(--el-fill-color-light, #f5f7fa);
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 12px;
}

.code-block {
  background: var(--el-fill-color-darker, #2b2b2b);
  color: #a9dc76;
  padding: 10px 16px;
  border-radius: 6px;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
}
</style>
