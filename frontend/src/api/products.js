import request from '@/utils/request'

export const getProducts = (params) => {
  return request({ url: '/api/products/', method: 'get', params })
}
