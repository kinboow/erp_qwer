import request from '@/utils/request'

export const getSalesOrders = (params, options = {}) => {
  return request({ url: '/api/sales-orders/', method: 'get', params, ...options })
}

export const getOrderDetail = (orderNo) => {
  return request({ url: `/api/sales-orders/${encodeURIComponent(orderNo)}`, method: 'get' })
}

export const getOrderItems = (orderNo) => {
  return request({ url: `/api/sales-orders/${encodeURIComponent(orderNo)}/items`, method: 'get' })
}

export const syncOrders = (daysBack = 360) => {
  return request({ url: '/api/erp/sync/trigger-orders', method: 'post', params: { days_back: daysBack }, timeout: 300000 })
}

export const printPicking = (orderNo) => {
  return request({ url: `/api/sales-orders/${encodeURIComponent(orderNo)}/print-picking`, method: 'post', timeout: 120000 })
}
