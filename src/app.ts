import express, { Application } from 'express';
import cors from 'cors';
import helmet from 'helmet';
import rateLimit from 'express-rate-limit';
import 'express-async-errors';
import { config } from './config';
import { logger } from './utils/logger';
import { errorMiddleware } from './middlewares/error.middleware';
import { mqService } from './services/mq.service';

// 导入路由
import authRoutes from './routes/auth.routes';
import userRoutes from './routes/user.routes';
import roleRoutes from './routes/role.routes';
import customerRoutes from './routes/customer.routes';
import logRoutes from './routes/log.routes';
import wechatCallbackRoutes from './routes/wechat-callback.routes';
import wechatWsRoutes from './routes/wechat-ws.routes';

class App {
  public app: Application;

  constructor() {
    this.app = express();
    this.initializeMiddlewares();
    this.initializeRoutes();
    this.initializeErrorHandling();
  }

  private initializeMiddlewares(): void {
    // 安全中间件
    this.app.use(helmet());

    // CORS
    this.app.use(cors());

    // 请求体解析
    this.app.use(express.json());
    this.app.use(express.urlencoded({ extended: true }));

    // 限流
    const limiter = rateLimit({
      windowMs: 15 * 60 * 1000, // 15分钟
      max: 100, // 限制100个请求
      message: '请求过于频繁，请稍后再试',
    });
    this.app.use('/api/', limiter);

    // 请求日志
    this.app.use((req, res, next) => {
      logger.info(`${req.method} ${req.path}`, {
        ip: req.ip,
        userAgent: req.get('user-agent'),
      });
      next();
    });
  }

  private initializeRoutes(): void {
    // 健康检查
    this.app.get('/health', (req, res) => {
      res.json({ status: 'ok', timestamp: new Date().toISOString() });
    });

    this.app.use('/api/wechat/callback', wechatCallbackRoutes);
    this.app.use('/api/wechat/ws', wechatWsRoutes);

    // API路由
    this.app.use('/api/auth', authRoutes);
    this.app.use('/api/users', userRoutes);
    this.app.use('/api/roles', roleRoutes);
    this.app.use('/api/customers', customerRoutes);
    this.app.use('/api/logs', logRoutes);

    // 404处理
    this.app.use((req, res) => {
      res.status(404).json({ code: 404, message: '接口不存在' });
    });
  }

  private initializeErrorHandling(): void {
    this.app.use(errorMiddleware);
  }

  public async start(): Promise<void> {
    try {
      // 初始化消息队列
      await mqService.connect();

      // 启动服务器
      this.app.listen(config.port, () => {
        logger.info(`Server is running on port ${config.port}`);
        logger.info(`Environment: ${config.env}`);
      });
    } catch (error) {
      logger.error('Failed to start server:', error);
      process.exit(1);
    }
  }
}

export default App;
