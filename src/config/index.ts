import dotenv from 'dotenv';

dotenv.config();

export const config = {
  // 服务器配置
  port: parseInt(process.env.PORT || '3000'),
  env: process.env.NODE_ENV || 'development',

  // 数据库配置
  database: {
    host: process.env.DB_HOST || 'localhost',
    port: parseInt(process.env.DB_PORT || '3306'),
    user: process.env.DB_USER || 'root',
    password: process.env.DB_PASSWORD || '',
    database: process.env.DB_NAME || 'factory_management',
    waitForConnections: true,
    connectionLimit: 10,
    queueLimit: 0,
  },

  // Redis配置
  redis: {
    host: process.env.REDIS_HOST || 'localhost',
    port: parseInt(process.env.REDIS_PORT || '6379'),
    password: process.env.REDIS_PASSWORD || '',
    db: parseInt(process.env.REDIS_DB || '0'),
  },

  // JWT配置
  jwt: {
    secret: process.env.JWT_SECRET || 'your_jwt_secret_key',
    expiresIn: process.env.JWT_EXPIRES_IN || '7d',
    refreshExpiresIn: process.env.JWT_REFRESH_EXPIRES_IN || '30d',
  },

  // OSS配置
  oss: {
    region: process.env.OSS_REGION || 'oss-cn-hangzhou',
    accessKeyId: process.env.OSS_ACCESS_KEY_ID || '',
    accessKeySecret: process.env.OSS_ACCESS_KEY_SECRET || '',
    bucket: process.env.OSS_BUCKET || '',
  },

  // 消息队列配置
  mq: {
    host: process.env.MQ_HOST || 'localhost',
    port: parseInt(process.env.MQ_PORT || '5672'),
    username: process.env.MQ_USER || 'guest',
    password: process.env.MQ_PASSWORD || 'guest',
    vhost: process.env.MQ_VHOST || '/',
  },

  // 日志配置
  log: {
    level: process.env.LOG_LEVEL || 'info',
  },
};
