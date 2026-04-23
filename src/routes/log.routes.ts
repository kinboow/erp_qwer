import { Router } from 'express';
import { LogController } from '../controllers/log.controller';
import { authMiddleware } from '../middlewares/auth.middleware';

const router = Router();
const logController = new LogController();

// 系统日志（读取日志文件）
router.get('/system', authMiddleware, (req, res) => logController.getSystemLogs(req, res));

// 操作日志（读取数据库）
router.get('/operation', authMiddleware, (req, res) => logController.getOperationLogs(req, res));

export default router;
