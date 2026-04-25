import request from '@/utils/request'

export const getErpSyncConfig = () => {
  return request({ url: '/api/erp/sync/config', method: 'get' })
}

export const saveErpSyncConfig = (data) => {
  return request({ url: '/api/erp/sync/config', method: 'put', data })
}

export const testErpConnection = (data) => {
  return request({ url: '/api/erp/sync/test-connection', method: 'post', data })
}

export const getErpSyncStatus = () => {
  return request({ url: '/api/erp/sync/status', method: 'get' })
}

export const triggerErpSync = (daysBack = 90) => {
  return request({ url: `/api/erp/sync/trigger?days_back=${daysBack}`, method: 'post', timeout: 300000 })
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

export const fetchQrImageUrl = async () => {
  const resp = await request({
    url: '/api/erp/sync/qr-image',
    method: 'get',
    responseType: 'blob',
  })
  return URL.createObjectURL(resp)
}
