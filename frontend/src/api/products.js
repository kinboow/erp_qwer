import request from '@/utils/request'

export const getProducts = (params) => {
  return request({ url: '/api/products/', method: 'get', params })
}

export const syncProducts = () => {
  return request({ url: '/api/erp/sync/trigger-products', method: 'post', timeout: 300000 })
}
