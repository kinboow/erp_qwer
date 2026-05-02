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
