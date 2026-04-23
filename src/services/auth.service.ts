import { db } from '../database';
import bcrypt from 'bcryptjs';
import { JwtUtil } from '../utils/jwt';
import { redis } from '../utils/redis';

export interface LoginDto {
  username: string;
  password: string;
}

export interface RegisterDto {
  username: string;
  password: string;
  realName: string;
  email?: string;
  phone?: string;
}

export class AuthService {
  async login(data: LoginDto, ip: string) {
    const { username, password } = data;

    // 查询用户
    const sql = 'SELECT * FROM users WHERE username = ? AND deleted_at IS NULL';
    const users = await db.query(sql, [username]);

    if (users.length === 0) {
      throw new Error('用户名或密码错误');
    }

    const user = users[0];

    // 检查用户状态
    if (user.status === 0) {
      throw new Error('账号已被禁用');
    }

    // 验证密码
    const isPasswordValid = await bcrypt.compare(password, user.password);
    if (!isPasswordValid) {
      throw new Error('用户名或密码错误');
    }

    // 生成token
    const accessToken = JwtUtil.generateAccessToken(user.id, user.username);
    const refreshToken = JwtUtil.generateRefreshToken(user.id, user.username);

    // 更新最后登录信息
    await db.query(
      'UPDATE users SET last_login_time = NOW(), last_login_ip = ? WHERE id = ?',
      [ip, user.id]
    );

    // 缓存用户信息
    await redis.set(`user:${user.id}`, JSON.stringify({
      id: user.id,
      username: user.username,
      realName: user.real_name,
      email: user.email,
    }), 7200);

    return {
      accessToken,
      refreshToken,
      user: {
        id: user.id,
        username: user.username,
        realName: user.real_name,
        email: user.email,
        phone: user.phone,
        avatar: user.avatar,
      },
    };
  }

  async register(data: RegisterDto) {
    const { username, password, realName, email, phone } = data;

    // 检查用户名是否存在
    const existingUser = await db.query(
      'SELECT id FROM users WHERE username = ? AND deleted_at IS NULL',
      [username]
    );

    if (existingUser.length > 0) {
      throw new Error('用户名已存在');
    }

    // 加密密码
    const hashedPassword = await bcrypt.hash(password, 10);

    // 插入用户
    const result = await db.query(
      'INSERT INTO users (username, password, real_name, email, phone) VALUES (?, ?, ?, ?, ?)',
      [username, hashedPassword, realName, email, phone]
    );

    return {
      id: result.insertId,
      username,
      realName,
    };
  }

  async logout(token: string) {
    // 将token加入黑名单
    const payload = JwtUtil.decodeToken(token);
    if (payload && typeof payload !== 'string') {
      const exp = payload.exp || 0;
      const ttl = Math.floor((new Date(exp * 1000).getTime() - Date.now()) / 1000);
      if (ttl > 0) {
        await redis.set(`blacklist:${token}`, '1', ttl);
      }
    }
  }

  async refreshToken(refreshToken: string) {
    const payload = JwtUtil.verifyToken(refreshToken);

    if (payload.type !== 'refresh') {
      throw new Error('令牌类型错误');
    }

    // 生成新的访问令牌
    const accessToken = JwtUtil.generateAccessToken(payload.userId, payload.username);

    return { accessToken };
  }

  async getUserInfo(userId: number) {
    // 尝试从缓存获取
    const cached = await redis.get(`user:${userId}`);
    if (cached) {
      return JSON.parse(cached);
    }

    // 从数据库查询
    const sql = `
      SELECT u.id, u.username, u.real_name, u.email, u.phone, u.avatar,
             GROUP_CONCAT(DISTINCT r.code) as roles
      FROM users u
      LEFT JOIN user_roles ur ON u.id = ur.user_id
      LEFT JOIN roles r ON ur.role_id = r.id
      WHERE u.id = ? AND u.deleted_at IS NULL
      GROUP BY u.id
    `;
    const users = await db.query(sql, [userId]);

    if (users.length === 0) {
      throw new Error('用户不存在');
    }

    const user = users[0];
    const userInfo = {
      id: user.id,
      username: user.username,
      realName: user.real_name,
      email: user.email,
      phone: user.phone,
      avatar: user.avatar,
      roles: user.roles ? user.roles.split(',') : [],
    };

    // 缓存用户信息
    await redis.set(`user:${userId}`, JSON.stringify(userInfo), 7200);

    return userInfo;
  }
}
