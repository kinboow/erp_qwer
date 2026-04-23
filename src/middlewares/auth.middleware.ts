import { Request, Response, NextFunction } from 'express';
import { JwtUtil } from '../utils/jwt';
import { redis } from '../utils/redis';

export interface AuthRequest extends Request {
  user?: {
    userId: number;
    username: string;
  };
}

export const authMiddleware = async (
  req: AuthRequest,
  res: Response,
  next: NextFunction
): Promise<void> => {
  try {
    const token = req.headers.authorization?.replace('Bearer ', '');

    if (!token) {
      res.status(401).json({ code: 401, message: '未提供认证令牌' });
      return;
    }

    // 验证token是否在黑名单中
    const isBlacklisted = await redis.exists(`blacklist:${token}`);
    if (isBlacklisted) {
      res.status(401).json({ code: 401, message: '令牌已失效' });
      return;
    }

    // 验证token
    const payload = JwtUtil.verifyToken(token);

    if (payload.type !== 'access') {
      res.status(401).json({ code: 401, message: '令牌类型错误' });
      return;
    }

    // 将用户信息附加到请求对象
    req.user = {
      userId: payload.userId,
      username: payload.username,
    };

    next();
  } catch (error) {
    res.status(401).json({ code: 401, message: '认证失败' });
  }
};
