import request from '@/utils/request'

export const getAiProviders = () => {
  return request({ url: '/api/ai/providers', method: 'get' })
}

export const getAiConfig = () => {
  return request({ url: '/api/ai/config', method: 'get' })
}

export const saveAiConfig = (data) => {
  return request({ url: '/api/ai/config', method: 'put', data })
}

export const testAiConnection = (data) => {
  return request({ url: '/api/ai/test', method: 'post', data, timeout: 30000 })
}

export const getAiCallLogs = (params) => {
  return request({ url: '/api/ai/call-logs', method: 'get', params })
}

export const getAiCircuitBreakerStatus = () => {
  return request({ url: '/api/ai/circuit-breaker/status', method: 'get' })
}

export const getAiBufferedMessages = () => {
  return request({ url: '/api/ai/circuit-breaker/buffered-messages', method: 'get' })
}

export const recoverAi = () => {
  return request({ url: '/api/ai/circuit-breaker/recover', method: 'post', timeout: 60000 })
}

export const reprocessAiMessages = (data) => {
  return request({ url: '/api/ai/circuit-breaker/reprocess', method: 'post', data, timeout: 120000 })
}
