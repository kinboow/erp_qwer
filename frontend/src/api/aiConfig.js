import request from '@/utils/request'

export const getAiConfig = () => {
  return request({ url: '/api/ai/config', method: 'get' })
}

export const saveAiConfig = (data) => {
  return request({ url: '/api/ai/config', method: 'put', data })
}

export const testAiConnection = () => {
  return request({ url: '/api/ai/test', method: 'post', timeout: 30000 })
}
