import App from './app';
import { logger } from './utils/logger';

const app = new App();

app.start().catch((error) => {
  logger.error('Application failed to start:', error);
  process.exit(1);
});

// 优雅关闭
process.on('SIGTERM', () => {
  logger.info('SIGTERM signal received: closing HTTP server');
  process.exit(0);
});

process.on('SIGINT', () => {
  logger.info('SIGINT signal received: closing HTTP server');
  process.exit(0);
});
