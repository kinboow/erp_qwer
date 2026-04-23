import { Request, Response } from 'express';
import { logger } from '../utils/logger';

export class WechatCallbackController {
  async receiveHttpMessage(req: Request, res: Response) {
    try {
      const instanceId = String(req.query.instanceId || req.body?.instanceId || '');

      logger.info('Received WeChat HTTP callback', {
        instanceId,
        query: req.query,
        headers: req.headers,
        body: req.body,
      });

      res.json({
        code: 200,
        message: '回调接收成功',
        data: {
          instanceId,
          received: true,
          timestamp: new Date().toISOString(),
        },
      });
    } catch (error: any) {
      logger.error('Failed to process WeChat HTTP callback', {
        error: error?.message,
        stack: error?.stack,
      });

      res.status(500).json({
        code: 500,
        message: '回调处理失败',
      });
    }
  }
}
