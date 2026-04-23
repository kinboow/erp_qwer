import jwt from 'jsonwebtoken';
import { config } from '../config';

export interface JwtPayload {
  userId: number;
  username: string;
  type: 'access' | 'refresh';
  exp?: number;
  iat?: number;
}

export class JwtUtil {
  static generateAccessToken(userId: number, username: string): string {
    const payload: JwtPayload = {
      userId,
      username,
      type: 'access',
    };
    return jwt.sign(payload, config.jwt.secret as string, {
      expiresIn: config.jwt.expiresIn as any,
    });
  }

  static generateRefreshToken(userId: number, username: string): string {
    const payload: JwtPayload = {
      userId,
      username,
      type: 'refresh',
    };
    return jwt.sign(payload, config.jwt.secret as string, {
      expiresIn: config.jwt.refreshExpiresIn as any,
    });
  }

  static verifyToken(token: string): JwtPayload {
    try {
      return jwt.verify(token, config.jwt.secret) as JwtPayload;
    } catch (error) {
      throw new Error('Invalid token');
    }
  }

  static decodeToken(token: string): JwtPayload | null {
    try {
      return jwt.decode(token) as JwtPayload;
    } catch (error) {
      return null;
    }
  }
}
