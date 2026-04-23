import request from '@/utils/request'

export const getErpSyncConfig = () => {
  return request({ url: '/api/erp/sync/config', method: 'get' })
}

export const saveErpSyncConfig = (data) => {
  return request({ url: '/api/erp/sync/config', method: 'put', data })
}

export const getErpSyncStatus = () => {
  return request({ url: '/api/erp/sync/status', method: 'get' })
}

export const triggerErpSync = (daysBack = 90) => {
  return request({ url: `/api/erp/sync/trigger?days_back=${daysBack}`, method: 'post' })
}

export const uploadErpQr = (file) => {
  const formData = new FormData()
  formData.append('file', file)
  return request({
    url: '/api/erp/sync/upload-qr',
    method: 'post',
    data: formData,
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}
