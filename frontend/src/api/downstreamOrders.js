import request from '@/utils/request'

export const getReviewList = (params) => {
  return request({
    url: '/api/downstream-orders/reviews',
    method: 'get',
    params
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

export const approveReview = (id, data) => {
  return request({
    url: `/api/downstream-orders/reviews/${id}/approve`,
    method: 'post',
    data
  })
}

export const replaceReview = (id, data) => {
  return request({
    url: `/api/downstream-orders/reviews/${id}/replace`,
    method: 'post',
    data
  })
}

export const manualReview = (id, data) => {
  return request({
    url: `/api/downstream-orders/reviews/${id}/manual`,
    method: 'post',
    data
  })
}

export const voidReview = (id, data) => {
  return request({
    url: `/api/downstream-orders/reviews/${id}/void`,
    method: 'post',
    data
  })
}
