import axios from 'axios'
import { ElMessage } from 'element-plus'
import router from '@/router'

const request = axios.create({
  baseURL: '',
  timeout: 10000
})

let isRedirectingToLogin = false

function handleTokenExpired() {
  if (isRedirectingToLogin) return
  isRedirectingToLogin = true

  localStorage.removeItem('token')
  localStorage.removeItem('userInfo')

  ElMessage.warning('登录已过期，请重新登录')

  router.push('/login').finally(() => {
    setTimeout(() => { isRedirectingToLogin = false }, 2000)
  })
}

// 请求拦截器
request.interceptors.request.use(
  config => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  error => {
    return Promise.reject(error)
  }
)

// 响应拦截器
request.interceptors.response.use(
  response => {
    const res = response.data
    if (res.code && res.code !== 200) {
      ElMessage.error(res.message || '请求失败')
      return Promise.reject(new Error(res.message || '请求失败'))
    }
    return res
  },
  error => {
    if (error.response) {
      const { status, data } = error.response
      if (status === 401) {
        const requestUrl = error.config?.url || ''
        const hasToken = !!localStorage.getItem('token')
        const isLogin = requestUrl.includes('/auth/login')
        const isLogout = error.config?.url?.includes('/auth/logout')
        if (isLogin) {
          ElMessage.error(data.detail || data.message || '用户名或密码错误')
        } else if (!isLogout && hasToken) {
          handleTokenExpired()
        } else {
          ElMessage.error(data.detail || data.message || '未授权访问')
        }
      } else if (status === 403) {
        ElMessage.error('权限不足')
      } else {
        ElMessage.error(data.detail || data.message || '请求失败')
      }
    } else {
      ElMessage.error('网络错误，请稍后重试')
    }
    return Promise.reject(error)
  }
)

export default request
