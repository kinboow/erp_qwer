import { Request, Response } from 'express';
import { wechatWsService } from '../services/wechat-ws.service';

export class WechatWsController {
  connect(req: Request, res: Response) {
    try {
      const { instanceId, url } = req.body;
      const result = wechatWsService.connect(String(instanceId || ''), String(url || ''));
      res.json({
        code: 200,
        message: 'WebSocket 连接已启动',
        data: result,
      });
    } catch (error: any) {
      res.status(400).json({
        code: 400,
        message: error.message || '启动 WebSocket 连接失败',
      });
    }
  }

  disconnect(req: Request, res: Response) {
    try {
      const { instanceId } = req.params;
      const ok = wechatWsService.disconnect(String(instanceId || ''));
      res.json({
        code: 200,
        message: ok ? 'WebSocket 连接已关闭' : '未找到对应连接',
      });
    } catch (error: any) {
      res.status(400).json({
        code: 400,
        message: error.message || '关闭 WebSocket 连接失败',
      });
    }
  }

  getStatus(req: Request, res: Response) {
    const { instanceId } = req.query;
    res.json({
      code: 200,
      message: '获取成功',
      data: wechatWsService.getStatus(instanceId ? String(instanceId) : undefined),
    });
  }
}
