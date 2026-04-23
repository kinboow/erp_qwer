import request from '@/utils/request'

// 获取用户列表
export const getUserList = (params) => {
  return request({
    url: '/api/users',
    method: 'get',
    params
  })
}

// 获取用户详情
export const getUserById = (id) => {
  return request({
    url: `/api/users/${id}`,
    method: 'get'
  })
}

// 创建用户
export const createUser = (data) => {
  return request({
    url: '/api/users',
    method: 'post',
    data
  })
}

// 更新用户
export const updateUser = (id, data) => {
  return request({
    url: `/api/users/${id}`,
    method: 'put',
    data
  })
}

// 删除用户
export const deleteUser = (id) => {
  return request({
    url: `/api/users/${id}`,
    method: 'delete'
  })
}
