import request from '@/utils/request'

export const getReviewList = (params, options = {}) => {
  return request({
    url: '/api/downstream-orders/reviews',
    method: 'get',
    params,
    ...options
  })
}

export const getReviewDetail = (id) => {
  return request({
    url: `/api/downstream-orders/reviews/${id}`,
    method: 'get'
  })
}

export const reparseReview = (id) => {
  return request({
    url: `/api/downstream-orders/reviews/${id}/reparse`,
    method: 'post'
  })
}

export const checkDuplicate = (id, data) => {
  return request({
    url: `/api/downstream-orders/reviews/${id}/check-duplicate`,
    method: 'post',
    data,
    timeout: 0
  })
}

export const approveReview = (id, data) => {
  return request({
    url: `/api/downstream-orders/reviews/${id}/approve`,
    method: 'post',
    data,
    timeout: 0
  })
}

export const replaceReview = (id, data) => {
  return request({
    url: `/api/downstream-orders/reviews/${id}/replace`,
    method: 'post',
    data,
    timeout: 0
  })
}

export const manualReview = (id, data) => {
  return request({
    url: `/api/downstream-orders/reviews/${id}/manual`,
    method: 'post',
    data,
    timeout: 0
  })
}

export const voidReview = (id, data) => {
  return request({
    url: `/api/downstream-orders/reviews/${id}/void`,
    method: 'post',
    data,
    timeout: 0
  })
}

export const revertPending = (id) => {
  return request({
    url: `/api/downstream-orders/reviews/${id}/revert-pending`,
    method: 'post'
  })
}

export const markModifyDone = (id, data) => {
  return request({
    url: `/api/downstream-orders/reviews/${id}/modify-done`,
    method: 'post',
    data
  })
}

export const getContextMessages = (id, options = {}) => {
  return request({
    url: `/api/downstream-orders/reviews/${id}/context-messages`,
    method: 'get',
    ...options
  })
}

