import request from '@/utils/request'

// 获取角色列表（分页）
export const getRoleList = (params) => {
  return request({
    url: '/api/roles',
    method: 'get',
    params
  })
}

// 获取所有角色（下拉列表用）
export const getAllRoles = () => {
  return request({
    url: '/api/roles/all',
    method: 'get'
  })
}

// 获取角色详情
export const getRoleById = (id) => {
  return request({
    url: `/api/roles/${id}`,
    method: 'get'
  })
}

// 创建角色
export const createRole = (data) => {
  return request({
    url: '/api/roles',
    method: 'post',
    data
  })
}

// 更新角色
export const updateRole = (id, data) => {
  return request({
    url: `/api/roles/${id}`,
    method: 'put',
    data
  })
}

// 删除角色
export const deleteRole = (id) => {
  return request({
    url: `/api/roles/${id}`,
    method: 'delete'
  })
}

// 获取权限树
export const getPermissionTree = () => {
  return request({
    url: '/api/roles/permissions',
    method: 'get'
  })
}
