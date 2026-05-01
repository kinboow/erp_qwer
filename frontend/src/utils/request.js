import axios from 'axios'
import { ElMessage } from 'element-plus'
import router from '@/router'

const request = axios.create({
  baseURL: '',
  timeout: 30000
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

// 从响应 data 中提取可读的错误消息字符串
function extractErrorMsg(data, fallback = '请求失败') {
  if (!data) return fallback
  // FastAPI 422 validation error: { detail: [{ msg: "...", ... }] }
  const detail = data.detail
  if (Array.isArray(detail)) {
    const msgs = detail.map(d => d?.msg || d?.message || '').filter(Boolean)
    return msgs.length > 0 ? msgs.join('; ') : fallback
  }
  const raw = detail || data.message || ''
  // 确保返回非空字符串
  const msg = typeof raw === 'string' ? raw.trim() : String(raw || '')
  return msg || fallback
}

// 响应拦截器
request.interceptors.response.use(
  response => {
    // blob 类型直接返回，不走 code 检查
    if (response.config.responseType === 'blob') {
      return response.data
    }
    const res = response.data
    const silentError = !!response.config?.silentError
    if (res.code && res.code !== 200) {
      const msg = res.message || '请求失败'
      if (!silentError) ElMessage.error(msg)
      return Promise.reject(new Error(msg))
    }
    return res
  },
  error => {
    const silentError = !!error.config?.silentError
    if (error.response) {
      const { status, data } = error.response
      if (status === 401) {
        const requestUrl = error.config?.url || ''
        const hasToken = !!localStorage.getItem('token')
        const isLogin = requestUrl.includes('/auth/login')
        const isLogout = error.config?.url?.includes('/auth/logout')
        if (isLogin) {
          if (!silentError) ElMessage.error(extractErrorMsg(data, '用户名或密码错误'))
        } else if (!isLogout && hasToken) {
          handleTokenExpired()
        } else {
          if (!silentError) ElMessage.error(extractErrorMsg(data, '未授权访问'))
        }
      } else if (status === 403) {
        if (!silentError) ElMessage.error(extractErrorMsg(data, '权限不足'))
      } else {
        if (!silentError) ElMessage.error(extractErrorMsg(data, '请求失败'))
      }
    } else {
      if (!silentError) ElMessage.error('网络错误，请稍后重试')
    }
    return Promise.reject(error)
  }
)

export default request
