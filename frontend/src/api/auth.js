import request from '@/utils/request'

// 登录
export const login = (data) => {
  return request({
    url: '/api/auth/login',
    method: 'post',
    data
  })
}

// 登出
export const logout = () => {
  return request({
    url: '/api/auth/logout',
    method: 'post'
  })
}

// 获取用户信息
export const getUserInfo = () => {
  return request({
    url: '/api/auth/userinfo',
    method: 'get'
  })
}
