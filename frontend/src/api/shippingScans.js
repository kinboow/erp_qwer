import request from '@/utils/request'

export const getScanRecords = (params) => {
  return request({
    url: '/api/shipping/scan-records',
    method: 'get',
    params
  })
}

export const getScanStats = () => {
  return request({
    url: '/api/shipping/scan-records/stats',
    method: 'get'
  })
}

export const approveScanRecord = (recordId, data) => {
  return request({
    url: `/api/shipping/scan-records/${recordId}/approve`,
    method: 'post',
    data
  })
}

export const voidScanRecord = (recordId, data) => {
  return request({
    url: `/api/shipping/scan-records/${recordId}/void`,
    method: 'post',
    data
  })
}
