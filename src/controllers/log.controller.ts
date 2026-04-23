import { Request, Response } from 'express';
import { LogService } from '../services/log.service';

const logService = new LogService();

export class LogController {
  async getSystemLogs(req: Request, res: Response): Promise<void> {
    try {
      const { page = '1', pageSize = '20', level, keyword, startDate, endDate } = req.query;

      const result = await logService.getSystemLogs({
        page: Number(page),
        pageSize: Number(pageSize),
        level: level as string,
        keyword: keyword as string,
        startDate: startDate as string,
        endDate: endDate as string,
      });

      res.json({ code: 200, data: result });
    } catch (error: any) {
      res.status(500).json({ code: 500, message: error.message || '获取系统日志失败' });
    }
  }

  async getOperationLogs(req: Request, res: Response): Promise<void> {
    try {
      const { page = '1', pageSize = '20', module, action, keyword, startDate, endDate } = req.query;

      const result = await logService.getOperationLogs({
        page: Number(page),
        pageSize: Number(pageSize),
        module: module as string,
        action: action as string,
        keyword: keyword as string,
        startDate: startDate as string,
        endDate: endDate as string,
      });

      res.json({ code: 200, data: result });
    } catch (error: any) {
      res.status(500).json({ code: 500, message: error.message || '获取操作日志失败' });
    }
  }
}
