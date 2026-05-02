import request from '@/utils/request'

export const getUnshippedReport = (params) => {
  return request({ url: '/api/unshipped-report', method: 'get', params })
}

export const cancelUnshipped = (ids) => {
  return request({ url: '/api/erp/unshipped-report/cancel', method: 'post', data: { ids } })
}

export const restoreUnshipped = (ids) => {
  return request({ url: '/api/erp/unshipped-report/restore', method: 'post', data: { ids } })
}

export const syncUnshippedReport = (daysBack = 360) => {
  return request({ url: '/api/erp/sync/trigger-unshipped', method: 'post', params: { days_back: daysBack } })
}
