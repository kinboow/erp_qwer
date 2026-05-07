import request from '@/utils/request'

export const getPrinterConfig = () => {
  return request({ url: '/api/printer/config', method: 'get' })
}

export const savePrinterConfig = (data) => {
  return request({ url: '/api/printer/config', method: 'put', data })
}

export const enqueuePrint = (orderNo, docType = 'picking') => {
  return request({ url: '/api/printer/queue/enqueue', method: 'post', data: { order_no: orderNo, doc_type: docType } })
}

export const getPrinterClients = () => {
  return request({ url: '/api/printer/clients', method: 'get' })
}

export const sendTestPrint = (targetClient, targetPrinter) => {
  return request({
    url: '/api/printer/test-print',
    method: 'post',
    data: { target_client: targetClient || '', target_printer: targetPrinter || '' },
  })
}

export const runScheduledTaskTest = () => {
  return request({ url: '/api/printer/schedule/test-run', method: 'post' })
}

export const getScheduledTaskLogs = (limit = 50) => {
  return request({ url: '/api/printer/schedule/logs', method: 'get', params: { limit } })
}
