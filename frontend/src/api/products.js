import request from '@/utils/request'

export const getProducts = (params) => {
  return request({ url: '/api/erp/products', method: 'get', params })
}
