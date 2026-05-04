import request from '@/utils/request'

// 获取企业微信实例列表
export const getInstances = () => {
  return request({
    url: '/api/wechat/instances',
    method: 'get'
  })
}

// 创建企业微信实例
export const createInstance = (data) => {
  return request({
    url: '/api/wechat/instances',
    method: 'post',
    data
  })
}

// 更新企业微信实例
export const updateInstance = (id, data) => {
  return request({
    url: `/api/wechat/instances/${id}`,
    method: 'put',
    data
  })
}

// 检测实例登录状态
export const checkInstanceStatus = (id) => {
  return request({
    url: `/api/wechat/instances/${id}/status`,
    method: 'get'
  })
}

// 删除企业微信实例
export const deleteInstance = (id) => {
  return request({
    url: `/api/wechat/instances/${id}`,
    method: 'delete'
  })
}

// 获取群聊列表（从企微API）
export const getRoomList = (instanceId) => {
  return request({
    url: `/api/wechat/instances/${instanceId}/rooms`,
    method: 'get'
  })
}

// 同步群聊到数据库
export const syncRooms = (instanceId) => {
  return request({
    url: `/api/wechat/instances/${instanceId}/sync-rooms`,
    method: 'post'
  })
}

// 获取监听配置列表
export const getListeners = (params) => {
  return request({
    url: '/api/wechat/listeners',
    method: 'get',
    params
  })
}

// 更新监听配置
export const updateListener = (id, data) => {
  return request({
    url: `/api/wechat/listeners/${id}`,
    method: 'put',
    data
  })
}

// 批量更新监听状态
export const batchUpdateListeners = (data) => {
  return request({
    url: '/api/wechat/listeners/batch',
    method: 'post',
    data
  })
}

export const connectWechatWs = (data) => {
  return request({
    url: '/api/wechat/ws/connect',
    method: 'post',
    data
  })
}

export const disconnectWechatWs = (instanceId) => {
  return request({
    url: `/api/wechat/ws/connect/${instanceId}`,
    method: 'delete'
  })
}

export const getWechatWsStatus = (params) => {
  return request({
    url: '/api/wechat/ws/status',
    method: 'get',
    params
  })
}

export const proxyStartWechat = (data) => {
  return request({
    url: '/api/wechat/proxy/start',
    method: 'post',
    data
  })
}

export const proxyWaitLogin = (data) => {
  return request({
    url: '/api/wechat/proxy/wait_login',
    method: 'post',
    data,
    timeout: 65000
  })
}

export const proxyRefreshQrcode = (data) => {
  return request({
    url: '/api/wechat/proxy/refresh_qrcode',
    method: 'post',
    data
  })
}

export const proxyLoginWindowScreenshot = (data) => {
  return request({
    url: '/api/wechat/proxy/login_window_screenshot',
    method: 'post',
    data,
    timeout: 20000
  })
}

export const getWechatGlobalConfig = () => {
  return request({
    url: '/api/wechat/config',
    method: 'get'
  })
}

export const saveWechatGlobalConfig = (data) => {
  return request({
    url: '/api/wechat/config',
    method: 'put',
    data
  })
}

// 获取已同步到数据库的群聊列表（不调用外部 API，速度快）
export const getSyncedRooms = () => {
  return request({
    url: '/api/wechat/rooms/synced',
    method: 'get'
  })
}

export const getRoomsAllStatus = () => {
  return request({
    url: '/api/wechat/rooms/all-status',
    method: 'get'
  })
}

// 获取所有客户群去重成员
export const getCustomerRoomMembers = () => {
  return request({
    url: '/api/wechat/customer-room-members',
    method: 'get',
    timeout: 60000
  })
}

// 获取已标记的员工企微账号
export const getEmployeeAccounts = () => {
  return request({
    url: '/api/wechat/employee-accounts',
    method: 'get'
  })
}

// 保存员工企微账号
export const saveEmployeeAccounts = (accounts) => {
  return request({
    url: '/api/wechat/employee-accounts',
    method: 'post',
    data: { accounts }
  })
}
