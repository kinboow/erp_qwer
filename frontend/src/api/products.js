import request from '@/utils/request'

export const getProducts = (params) => {
  return request({ url: '/api/products/', method: 'get', params })
}

export const syncProducts = () => {
  return request({ url: '/api/erp/sync/trigger-products', method: 'post', timeout: 300000 })
}

export const getNameMappings = (productNo) => {
  return request({ url: `/api/products/${encodeURIComponent(productNo)}/name-mappings`, method: 'get' })
}

export const addNameMapping = (productNo, aliasName) => {
  return request({ url: `/api/products/${encodeURIComponent(productNo)}/name-mappings`, method: 'post', data: { alias_name: aliasName } })
}

export const deleteNameMapping = (mappingId) => {
  return request({ url: `/api/products/name-mappings/${mappingId}`, method: 'delete' })
}
