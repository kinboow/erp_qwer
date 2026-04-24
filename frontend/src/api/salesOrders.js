import request from '@/utils/request'

export const getSalesOrders = (params) => {
  return request({ url: '/api/sales-orders/', method: 'get', params })
}

export const getOrderDetail = (orderNo) => {
  return request({ url: `/api/sales-orders/${encodeURIComponent(orderNo)}`, method: 'get' })
}

export const getOrderItems = (orderNo) => {
  return request({ url: `/api/sales-orders/${encodeURIComponent(orderNo)}/items`, method: 'get' })
}
