import { Request, Response, NextFunction } from 'express';
import { db } from '../database';
import { AuthRequest } from './auth.middleware';
import { redis } from '../utils/redis';

export const permissionMiddleware = (requiredPermission: string) => {
  return async (req: AuthRequest, res: Response, next: NextFunction): Promise<void> => {
    try {
      if (!req.user) {
        res.status(401).json({ code: 401, message: '未认证' });
        return;
      }

      const { userId } = req.user;

      // 尝试从缓存获取用户权限
      const cacheKey = `user:permissions:${userId}`;
      let permissions = await redis.get(cacheKey);

      if (!permissions) {
        // 先查询用户的角色编码
        const roleSql = `
          SELECT DISTINCT r.code
          FROM roles r
          INNER JOIN user_roles ur ON r.id = ur.role_id
          WHERE ur.user_id = ? AND r.status = 1
        `;
        const roleRows = await db.query(roleSql, [userId]);
        const roleCodes = roleRows.map((row: any) => row.code);

        // 从数据库查询用户权限
        const sql = `
          SELECT DISTINCT p.code
          FROM permissions p
          INNER JOIN role_permissions rp ON p.id = rp.permission_id
          INNER JOIN user_roles ur ON rp.role_id = ur.role_id
          WHERE ur.user_id = ? AND p.status = 1
        `;
        const rows = await db.query(sql, [userId]);
        const permissionCodes = rows.map((row: any) => row.code);

        // 如果用户拥有超级管理员角色，添加通配符权限
        if (roleCodes.includes('super_admin')) {
          permissionCodes.push('*');
        }

        // 缓存权限列表（1小时）
        await redis.set(cacheKey, JSON.stringify(permissionCodes), 3600);
        permissions = JSON.stringify(permissionCodes);
      }

      const permissionList: string[] = JSON.parse(permissions);

      // 检查是否有超级管理员权限
      if (permissionList.includes('*') || permissionList.includes('super_admin')) {
        next();
        return;
      }

      // 检查是否有所需权限
      if (!permissionList.includes(requiredPermission)) {
        res.status(403).json({ code: 403, message: '权限不足' });
        return;
      }

      next();
    } catch (error) {
      res.status(500).json({ code: 500, message: '权限验证失败' });
    }
  };
};
