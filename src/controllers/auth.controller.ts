import { Request, Response } from 'express';
import { AuthService } from '../services/auth.service';
import { LogService } from '../services/log.service';
import { AuthRequest } from '../middlewares/auth.middleware';

const authService = new AuthService();

export class AuthController {
  async login(req: Request, res: Response) {
    try {
      const { username, password } = req.body;

      if (!username || !password) {
        return res.status(400).json({ code: 400, message: '用户名和密码不能为空' });
      }

      const ip = req.ip || req.socket.remoteAddress || '';
      const result = await authService.login({ username, password }, ip);

      res.json({
        code: 200,
        message: '登录成功',
        data: result,
      });

      LogService.record({
        user_id: result.user?.id || 0,
        username,
        module: 'auth',
        action: 'login',
        description: `用户 ${username} 登录系统`,
        ip: String(ip),
      }).catch(() => {});
    } catch (error: any) {
      res.status(400).json({ code: 400, message: error.message });
    }
  }

  async register(req: Request, res: Response) {
    try {
      const { username, password, realName, email, phone } = req.body;

      if (!username || !password || !realName) {
        return res.status(400).json({ code: 400, message: '用户名、密码和真实姓名不能为空' });
      }

      const result = await authService.register({ username, password, realName, email, phone });

      res.json({
        code: 200,
        message: '注册成功',
        data: result,
      });
    } catch (error: any) {
      res.status(400).json({ code: 400, message: error.message });
    }
  }

  async logout(req: AuthRequest, res: Response) {
    try {
      const token = req.headers.authorization?.replace('Bearer ', '') || '';
      await authService.logout(token);

      res.json({
        code: 200,
        message: '退出成功',
      });

      LogService.record({
        user_id: req.user?.userId || 0,
        username: req.user?.username || '',
        module: 'auth',
        action: 'logout',
        description: `用户 ${req.user?.username || ''} 退出系统`,
        ip: String(req.ip || ''),
      }).catch(() => {});
    } catch (error: any) {
      res.status(400).json({ code: 400, message: error.message });
    }
  }

  async refreshToken(req: Request, res: Response) {
    try {
      const { refreshToken } = req.body;

      if (!refreshToken) {
        return res.status(400).json({ code: 400, message: '刷新令牌不能为空' });
      }

      const result = await authService.refreshToken(refreshToken);

      res.json({
        code: 200,
        message: '刷新成功',
        data: result,
      });
    } catch (error: any) {
      res.status(400).json({ code: 400, message: error.message });
    }
  }

  async getUserInfo(req: AuthRequest, res: Response) {
    try {
      if (!req.user) {
        return res.status(401).json({ code: 401, message: '未认证' });
      }

      const userInfo = await authService.getUserInfo(req.user.userId);

      res.json({
        code: 200,
        message: '获取成功',
        data: userInfo,
      });
    } catch (error: any) {
      res.status(400).json({ code: 400, message: error.message });
    }
  }
}
