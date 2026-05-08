export function buildBackendWsUrl(path = '/ws/notify') {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'

  // 开发环境：前端跑在 Vite(5173) 时，直接连后端 8900，避免 ws 代理异常
  if (location.port === '5173') {
    return `${proto}://${location.hostname}:8900${normalizedPath}`
  }

  return `${proto}://${location.host}${normalizedPath}`
}
