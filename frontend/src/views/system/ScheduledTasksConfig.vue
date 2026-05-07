<template>
  <div class="scheduled-task-config">
    <div class="config-section">
      <div class="section-title">
        <el-icon><Timer /></el-icon>
        <span>定时任务</span>
      </div>

      <div class="row-item">
        <div class="label">每日自动打印昨天下单未发货订单</div>
        <el-switch v-model="scheduleEnabled" active-text="已启用" inactive-text="未启用" />
      </div>

      <div class="row-item">
        <div class="label">执行时间</div>
        <el-time-select
          v-model="scheduleTime"
          style="width: 100%"
          start="00:00"
          step="00:05"
          end="23:55"
          placeholder="请选择每日执行时间"
        />
      </div>

      <div class="schedule-tip">
        系统会在你设置的时间，每天自动执行定时任务：包括“昨天下单且当前仍未发货订单逐单打印”以及“第三天未完全发货订单通知群提醒”。保存或修改后从次日开始生效。
      </div>

      <div v-if="effectiveDate" class="effective-tip">当前配置生效日期：{{ effectiveDate }}</div>

      <div class="form-actions">
        <el-button :icon="Refresh" @click="handleTestRun" :loading="testing">测试执行</el-button>
        <el-button type="primary" :icon="Check" @click="handleSave" :loading="saving">保存配置</el-button>
      </div>
    </div>

    <div class="config-section">
      <div class="section-title">
        <el-icon><Document /></el-icon>
        <span>任务日志</span>
      </div>

      <div class="log-toolbar">
        <div class="schedule-tip">显示每天任务的运行情况、运行结果和执行日志。</div>
        <el-button text :icon="Refresh" @click="loadLogs" :loading="logsLoading">刷新</el-button>
      </div>

      <el-empty v-if="!logsLoading && taskLogs.length === 0" description="暂无任务日志" />

      <div v-else class="log-list" v-loading="logsLoading">
        <el-card v-for="item in taskLogs" :key="item.id" shadow="never" class="log-card">
          <div class="log-header">
            <div class="log-meta">
              <div class="log-title">{{ taskNameText(item.task_key) }}</div>
              <div class="log-subtitle">
                <span>摘要：{{ item.summary || '-' }}</span>
                <span>运行日期：{{ item.run_date || '-' }}</span>
                <span>统计日期：{{ item.target_date || '-' }}</span>
                <span>触发方式：{{ triggerTypeText(item.trigger_type) }}</span>
                <span>执行时间：{{ item.created_at || '-' }}</span>
              </div>
            </div>
            <el-tag :type="statusTagType(item.status)">{{ statusText(item.status) }}</el-tag>
          </div>

          <div class="log-result-row">
            <span>结果：</span>
            <span>{{ formatResult(item) }}</span>
          </div>

          <el-collapse>
            <el-collapse-item title="查看详细日志" :name="String(item.id)">
              <pre class="log-text">{{ item.log_text || '暂无详细日志' }}</pre>
            </el-collapse-item>
          </el-collapse>
        </el-card>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Timer, Check, Refresh, Document } from '@element-plus/icons-vue'
import { getPrinterConfig, savePrinterConfig, runScheduledTaskTest, getScheduledTaskLogs } from '@/api/printer'

const saving = ref(false)
const testing = ref(false)
const logsLoading = ref(false)
const scheduleEnabled = ref(false)
const scheduleTime = ref('09:00')
const taskLogs = ref([])
const effectiveDate = ref('')

async function loadConfig() {
  try {
    const res = await getPrinterConfig()
    const cfg = res.data || {}
    scheduleEnabled.value = cfg.printer_unshipped_schedule_enabled === 'true'
    scheduleTime.value = cfg.printer_unshipped_schedule_time || '09:00'
    effectiveDate.value = cfg.printer_unshipped_schedule_effective_date || ''
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || '加载定时任务配置失败')
  }
}

async function handleSave() {
  if (!scheduleTime.value) {
    ElMessage.warning('请先选择定时任务执行时间')
    return
  }
  saving.value = true
  try {
    const res = await savePrinterConfig({
      printer_unshipped_schedule_enabled: scheduleEnabled.value ? 'true' : 'false',
      printer_unshipped_schedule_time: scheduleTime.value || '09:00',
    })
    effectiveDate.value = res?.data?.printer_unshipped_schedule_effective_date || effectiveDate.value
    ElMessage.success(`定时任务配置已保存，将于 ${effectiveDate.value || '次日'} 生效`)
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function handleTestRun() {
  testing.value = true
  try {
    const res = await runScheduledTaskTest()
    ElMessage.success(res?.message || '定时任务测试执行完成')
    await loadLogs()
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || '测试执行失败')
  } finally {
    testing.value = false
  }
}

async function loadLogs() {
  logsLoading.value = true
  try {
    const res = await getScheduledTaskLogs(50)
    taskLogs.value = res.data || []
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || '加载任务日志失败')
  } finally {
    logsLoading.value = false
  }
}

function statusText(status) {
  const map = { success: '成功', failed: '失败', running: '执行中' }
  return map[status] || status || '-'
}

function statusTagType(status) {
  const map = { success: 'success', failed: 'danger', running: 'warning' }
  return map[status] || 'info'
}

function triggerTypeText(triggerType) {
  const map = {
    scheduled: '定时触发',
    startup_catchup: '启动补跑',
    manual_test: '手动测试',
  }
  return map[triggerType] || triggerType || '-'
}

function taskNameText(taskKey) {
  const map = {
    unshipped_daily: '昨日未发货自动打印',
    third_day_unshipped_notify: '第三天未完全发货提醒',
  }
  return map[taskKey] || taskKey || '任务执行记录'
}

function formatResult(item) {
  const result = item?.result || {}
  if (item?.status === 'failed') {
    return result?.error || item?.summary || '执行失败'
  }
  if (typeof result?.sent_group_count === 'number') {
    return `提醒 ${result.order_count || 0} 个订单，通知群成功发送 ${result.sent_group_count} 次，客户确认消息成功发送 ${result.sent_customer_count || 0} 次`
  }
  if (typeof result?.queued_count === 'number') {
    return `入队 ${result.queued_count} 个订单${result.order_count != null ? `，匹配 ${result.order_count} 个订单` : ''}`
  }
  return item?.summary || '-'
}

onMounted(async () => {
  await loadConfig()
  await loadLogs()
})
</script>

<style scoped>
.scheduled-task-config {
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

.schedule-tip {
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.7;
  color: var(--lark-text-secondary, #646a73);
}

.effective-tip {
  margin-top: 8px;
  font-size: 12px;
  color: var(--el-color-primary, #409eff);
}

.form-actions {
  display: flex;
  gap: 12px;
  margin-top: 16px;
}

.log-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.log-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.log-card {
  border: 1px solid var(--lark-border-light, #e5e6eb);
}

.log-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.log-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--lark-text-primary, #1f2329);
}

.log-subtitle {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 6px;
  font-size: 12px;
  color: var(--lark-text-secondary, #646a73);
}

.log-result-row {
  margin-bottom: 8px;
  font-size: 13px;
  color: var(--lark-text-regular, #4e5969);
}

.log-text {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  line-height: 1.7;
  color: var(--lark-text-primary, #1f2329);
  background: var(--lark-bg-body, #f5f6f7);
  border-radius: 6px;
  padding: 12px;
}
</style>
