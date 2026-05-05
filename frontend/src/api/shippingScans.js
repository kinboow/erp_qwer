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
