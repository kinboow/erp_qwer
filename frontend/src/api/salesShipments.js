import request from '@/utils/request'

export const getSalesShipments = (params) => {
  return request({ url: '/api/sales-shipments/', method: 'get', params })
}

export const getShipmentDetail = (orderNo) => {
  return request({ url: `/api/sales-shipments/${encodeURIComponent(orderNo)}`, method: 'get' })
}

export const getShipmentItems = (orderNo) => {
  return request({ url: `/api/sales-shipments/${encodeURIComponent(orderNo)}/items`, method: 'get' })
}

export const syncShipments = (daysBack = 90) => {
  return request({ url: '/api/erp/sync/trigger-shipments', method: 'post', params: { days_back: daysBack }, timeout: 300000 })
}
