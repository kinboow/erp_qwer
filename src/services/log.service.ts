import * as fs from 'fs';
import * as path from 'path';
import * as readline from 'readline';
import { db } from '../database';

interface SystemLogQuery {
  page: number;
  pageSize: number;
  level?: string;
  keyword?: string;
  startDate?: string;
  endDate?: string;
}

interface OperationLogQuery {
  page: number;
  pageSize: number;
  module?: string;
  action?: string;
  keyword?: string;
  startDate?: string;
  endDate?: string;
}

interface SystemLogEntry {
  timestamp: string;
  level: string;
  service: string;
  message: string;
}

export class LogService {
  /**
   * 读取系统日志文件（winston JSON 格式），支持筛选和分页
   */
  async getSystemLogs(query: SystemLogQuery) {
    const logFile = path.resolve(process.cwd(), 'logs', 'combined.log');

    if (!fs.existsSync(logFile)) {
      return { list: [], total: 0 };
    }

    const allEntries: SystemLogEntry[] = [];

    const stream = fs.createReadStream(logFile, { encoding: 'utf-8' });
    const rl = readline.createInterface({ input: stream, crlfDelay: Infinity });

    for await (const line of rl) {
      if (!line.trim()) continue;
      try {
        const entry = JSON.parse(line);
        const logEntry: SystemLogEntry = {
          timestamp: entry.timestamp || '',
          level: entry.level || 'info',
          service: entry.service || '',
          message: entry.message || '',
        };

        // 级别过滤
        if (query.level && logEntry.level !== query.level) continue;

        // 关键词过滤
        if (query.keyword && !logEntry.message.toLowerCase().includes(query.keyword.toLowerCase())) continue;

        // 日期过滤
        if (query.startDate && logEntry.timestamp < query.startDate) continue;
        if (query.endDate && logEntry.timestamp < query.endDate + 'T23:59:59') {
          // 在范围内，不跳过
        } else if (query.endDate && logEntry.timestamp > query.endDate + 'T23:59:59') {
          continue;
        }

        allEntries.push(logEntry);
      } catch {
        // 跳过非 JSON 行
      }
    }

    // 按时间倒序
    allEntries.reverse();

    const total = allEntries.length;
    const start = (query.page - 1) * query.pageSize;
    const list = allEntries.slice(start, start + query.pageSize);

    return { list, total };
  }

  /**
   * 查询操作日志（数据库）
   */
  async getOperationLogs(query: OperationLogQuery) {
    const conditions: string[] = [];
    const params: any[] = [];

    if (query.module) {
      conditions.push('module = ?');
      params.push(query.module);
    }
    if (query.action) {
      conditions.push('action = ?');
      params.push(query.action);
    }
    if (query.keyword) {
      conditions.push('(username LIKE ? OR description LIKE ?)');
      params.push(`%${query.keyword}%`, `%${query.keyword}%`);
    }
    if (query.startDate) {
      conditions.push('created_at >= ?');
      params.push(query.startDate + ' 00:00:00');
    }
    if (query.endDate) {
      conditions.push('created_at <= ?');
      params.push(query.endDate + ' 23:59:59');
    }

    const where = conditions.length > 0 ? 'WHERE ' + conditions.join(' AND ') : '';

    // 总数
    const countSql = `SELECT COUNT(*) as total FROM operation_logs ${where}`;
    const countResult = await db.query(countSql, params);
    const total = countResult[0]?.total || 0;

    // 分页
    const offset = (query.page - 1) * query.pageSize;
    const dataSql = `SELECT id, username, module, action, description, ip, created_at FROM operation_logs ${where} ORDER BY created_at DESC LIMIT ${Number(query.pageSize)} OFFSET ${Number(offset)}`;
    const list = await db.query(dataSql, params);

    return { list, total };
  }

  /**
   * 记录操作日志
   */
  static async record(data: {
    user_id: number;
    username: string;
    module: string;
    action: string;
    description: string;
    ip?: string;
  }) {
    const sql = `INSERT INTO operation_logs (user_id, username, module, action, description, ip, created_at) VALUES (?, ?, ?, ?, ?, ?, NOW())`;
    await db.query(sql, [data.user_id, data.username, data.module, data.action, data.description, data.ip || '']);
  }
}
