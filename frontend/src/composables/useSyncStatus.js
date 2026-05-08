import { ref, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { buildBackendWsUrl } from '@/utils/backendUrl'
import request from '@/utils/request'

/**
 * 同步状态 composable — 提供模块同步锁检查 + WebSocket 自动刷新
 * @param {string} module  模块名: orders | shipments | products | inventory
 * @param {Function} onSyncComplete  同步完成后的回调（通常是 fetchXxx）
 */
const MODULE_LABELS = {
  orders: '销售订单',
  shipments: '发货单',
  products: '产品',
  inventory: '库存',
  unshipped: '待发货报表',
}

export function useSyncStatus(module, onSyncComplete) {
  const syncing = ref(false)
  const trigger = ref('')   // 'scheduled' | 'manual' | ''
  let notifyWs = null
  let reconnectTimer = null

  // 检查模块是否正在同步
  async function checkSyncStatus() {
    try {
      const res = await request({ url: '/api/erp/sync/module-status', method: 'get', silentError: true })
      const data = res.data || {}
      const info = data[module]
      if (info && typeof info === 'object') {
        syncing.value = !!info.syncing
        trigger.value = info.trigger || ''
      } else {
        syncing.value = !!info
        trigger.value = ''
      }
    } catch {
      // ignore
    }
  }

  // WebSocket 连接 — 监听 sync_complete 事件
  function connectWs() {
    if (notifyWs && notifyWs.readyState <= 1) return
    notifyWs = new WebSocket(buildBackendWsUrl('/ws/notify'))
    notifyWs.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data)
        if (msg.event === 'sync_complete' && msg.data?.module === module) {
          const isScheduled = msg.data?.trigger === 'scheduled'
          // 定时同步不弹窗，仅手动触发时弹窗提示
          if (!isScheduled) {
            const label = MODULE_LABELS[module] || module
            if (msg.data?.success) {
              ElMessage.success(`${label}同步完成`)
            } else {
              ElMessage.error(`${label}同步失败`)
            }
          }
          syncing.value = false
          trigger.value = ''
          if (typeof onSyncComplete === 'function') {
            onSyncComplete()
          }
        }
      } catch {}
    }
    notifyWs.onclose = () => {
      reconnectTimer = setTimeout(connectWs, 3000)
    }
    notifyWs.onerror = () => {
      notifyWs?.close()
    }
  }

  function disconnectWs() {
    if (reconnectTimer) clearTimeout(reconnectTimer)
    reconnectTimer = null
    if (notifyWs) {
      notifyWs.onclose = null
      notifyWs.close()
      notifyWs = null
    }
  }

  onMounted(() => {
    checkSyncStatus()
    connectWs()
  })

  onUnmounted(() => {
    disconnectWs()
  })

  return { syncing, trigger, checkSyncStatus }
}
