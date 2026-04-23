import { db } from '../database';
import bcrypt from 'bcryptjs';
import { redis } from '../utils/redis';

export interface CreateUserDto {
  username: string;
  password: string;
  realName: string;
  email?: string;
  phone?: string;
  roleIds?: number[];
}

export interface UpdateUserDto {
  realName?: string;
  email?: string;
  phone?: string;
  avatar?: string;
  status?: number;
  roleIds?: number[];
}

export class UserService {
  async getUserList(page: number = 1, pageSize: number = 10, keyword?: string) {
    const offset = (page - 1) * pageSize;

    let sql = `
      SELECT u.id, u.username, u.real_name, u.email, u.phone, u.avatar, u.status,
             u.last_login_time, u.last_login_ip, u.created_at,
             GROUP_CONCAT(DISTINCT r.name) as roles
      FROM users u
      LEFT JOIN user_roles ur ON u.id = ur.user_id
      LEFT JOIN roles r ON ur.role_id = r.id
      WHERE u.deleted_at IS NULL
    `;

    const params: any[] = [];

    if (keyword) {
      sql += ' AND (u.username LIKE ? OR u.real_name LIKE ? OR u.email LIKE ?)';
      const searchTerm = `%${keyword}%`;
      params.push(searchTerm, searchTerm, searchTerm);
    }

    sql += ' GROUP BY u.id ORDER BY u.created_at DESC LIMIT ? OFFSET ?';
    params.push(pageSize, offset);

    const users = await db.query(sql, params);

    // 获取总数
    let countSql = 'SELECT COUNT(*) as total FROM users WHERE deleted_at IS NULL';
    const countParams: any[] = [];

    if (keyword) {
      countSql += ' AND (username LIKE ? OR real_name LIKE ? OR email LIKE ?)';
      const searchTerm = `%${keyword}%`;
      countParams.push(searchTerm, searchTerm, searchTerm);
    }

    const countResult = await db.query(countSql, countParams);
    const total = countResult[0].total;

    return {
      list: users.map((user: any) => ({
        ...user,
        roles: user.roles ? user.roles.split(',') : [],
      })),
      total,
      page,
      pageSize,
    };
  }

  async getUserById(id: number) {
    const sql = `
      SELECT u.*, GROUP_CONCAT(DISTINCT ur.role_id) as role_ids
      FROM users u
      LEFT JOIN user_roles ur ON u.id = ur.user_id
      WHERE u.id = ? AND u.deleted_at IS NULL
      GROUP BY u.id
    `;
    const users = await db.query(sql, [id]);

    if (users.length === 0) {
      throw new Error('用户不存在');
    }

    const user = users[0];
    return {
      ...user,
      roleIds: user.role_ids ? user.role_ids.split(',').map(Number) : [],
    };
  }

  async createUser(data: CreateUserDto) {
    const { username, password, realName, email, phone, roleIds } = data;

    // 检查用户名是否存在
    const existing = await db.query(
      'SELECT id FROM users WHERE username = ? AND deleted_at IS NULL',
      [username]
    );

    if (existing.length > 0) {
      throw new Error('用户名已存在');
    }

    // 加密密码
    const hashedPassword = await bcrypt.hash(password, 10);

    return await db.transaction(async (conn: any) => {
      // 插入用户
      const [result]: any = await conn.execute(
        'INSERT INTO users (username, password, real_name, email, phone) VALUES (?, ?, ?, ?, ?)',
        [username, hashedPassword, realName, email, phone]
      );

      const userId = result.insertId;

      // 分配角色
      if (roleIds && roleIds.length > 0) {
        for (const roleId of roleIds) {
          await conn.execute(
            'INSERT INTO user_roles (user_id, role_id) VALUES (?, ?)',
            [userId, roleId]
          );
        }
      }

      return { id: userId, username, realName };
    });
  }

  async updateUser(id: number, data: UpdateUserDto) {
    const { realName, email, phone, avatar, status, roleIds } = data;

    return await db.transaction(async (conn) => {
      // 更新用户基本信息
      const updates: string[] = [];
      const params: any[] = [];

      if (realName !== undefined) {
        updates.push('real_name = ?');
        params.push(realName);
      }
      if (email !== undefined) {
        updates.push('email = ?');
        params.push(email);
      }
      if (phone !== undefined) {
        updates.push('phone = ?');
        params.push(phone);
      }
      if (avatar !== undefined) {
        updates.push('avatar = ?');
        params.push(avatar);
      }
      if (status !== undefined) {
        updates.push('status = ?');
        params.push(status);
      }

      if (updates.length > 0) {
        params.push(id);
        await conn.execute(
          `UPDATE users SET ${updates.join(', ')} WHERE id = ?`,
          params
        );
      }

      // 更新角色
      if (roleIds !== undefined) {
        await conn.execute('DELETE FROM user_roles WHERE user_id = ?', [id]);

        if (roleIds.length > 0) {
          for (const roleId of roleIds) {
            await conn.execute(
              'INSERT INTO user_roles (user_id, role_id) VALUES (?, ?)',
              [id, roleId]
            );
          }
        }
      }

      // 清除缓存
      await redis.del(`user:${id}`);
      await redis.del(`user:permissions:${id}`);
    });
  }

  async deleteUser(id: number) {
    // 软删除
    await db.query('UPDATE users SET deleted_at = NOW() WHERE id = ?', [id]);

    // 清除缓存
    await redis.del(`user:${id}`);
    await redis.del(`user:permissions:${id}`);
  }

  async resetPassword(id: number, newPassword: string) {
    const hashedPassword = await bcrypt.hash(newPassword, 10);
    await db.query('UPDATE users SET password = ? WHERE id = ?', [hashedPassword, id]);
  }
}
