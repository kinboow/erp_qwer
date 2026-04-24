import request from '@/utils/request'

export const getCustomerList = (params) => {
  return request({
    url: '/api/customers',
    method: 'get',
    params
  })
}

export const getCustomerById = (id) => {
  return request({
    url: `/api/customers/${id}`,
    method: 'get'
  })
}

export const createCustomer = (data) => {
  return request({
    url: '/api/customers',
    method: 'post',
    data
  })
}

export const updateCustomer = (id, data) => {
  return request({
    url: `/api/customers/${id}`,
    method: 'put',
    data
  })
}

export const deleteCustomer = (id) => {
  return request({
    url: `/api/customers/${id}`,
    method: 'delete'
  })
}

export const syncCustomersFromErp = () => {
  return request({
    url: '/api/customers/sync',
    method: 'post',
    timeout: 120000,
  })
}
