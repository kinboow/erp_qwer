import mysql from 'mysql2/promise';
import { config } from '../config';

class Database {
  private pool: mysql.Pool;

  constructor() {
    this.pool = mysql.createPool(config.database);
  }

  async query(sql: string, params?: any[]): Promise<any> {
    const connection = await this.pool.getConnection();
    try {
      const [rows] = await connection.query(sql, params);
      return rows;
    } finally {
      connection.release();
    }
  }

  async transaction(callback: (connection: mysql.PoolConnection) => Promise<any>): Promise<any> {
    const connection = await this.pool.getConnection();
    try {
      await connection.beginTransaction();
      const result = await callback(connection);
      await connection.commit();
      return result;
    } catch (error) {
      await connection.rollback();
      throw error;
    } finally {
      connection.release();
    }
  }

  async close(): Promise<void> {
    await this.pool.end();
  }
}

export const db = new Database();
