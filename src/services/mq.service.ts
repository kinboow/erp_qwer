import amqp from 'amqplib';
import { config } from '../config';
import { logger } from '../utils/logger';

class MessageQueueService {
  private connection: amqp.ChannelModel | null = null;
  private channel: amqp.Channel | null = null;

  async connect(): Promise<void> {
    try {
      const url = `amqp://${config.mq.username}:${config.mq.password}@${config.mq.host}:${config.mq.port}${config.mq.vhost}`;
      this.connection = await amqp.connect(url);
      this.channel = await this.connection.createChannel();

      logger.info('RabbitMQ connected successfully');

      this.connection.on('error', (err) => {
        logger.error('RabbitMQ connection error:', err);
      });

      this.connection.on('close', () => {
        logger.warn('RabbitMQ connection closed');
      });
    } catch (error) {
      logger.error('Failed to connect to RabbitMQ:', error);
      throw error;
    }
  }

  async assertQueue(queueName: string, options?: amqp.Options.AssertQueue): Promise<void> {
    if (!this.channel) {
      throw new Error('Channel not initialized');
    }
    await this.channel.assertQueue(queueName, options);
  }

  async sendToQueue(queueName: string, message: any): Promise<boolean> {
    if (!this.channel) {
      throw new Error('Channel not initialized');
    }

    const content = Buffer.from(JSON.stringify(message));
    return this.channel.sendToQueue(queueName, content, {
      persistent: true,
    });
  }

  async consume(
    queueName: string,
    callback: (message: any) => Promise<void>
  ): Promise<void> {
    if (!this.channel) {
      throw new Error('Channel not initialized');
    }

    await this.channel.consume(queueName, async (msg) => {
      if (msg) {
        try {
          const content = JSON.parse(msg.content.toString());
          await callback(content);
          this.channel!.ack(msg);
        } catch (error) {
          logger.error('Error processing message:', error);
          this.channel!.nack(msg, false, false);
        }
      }
    });
  }

  async publish(exchange: string, routingKey: string, message: any): Promise<boolean> {
    if (!this.channel) {
      throw new Error('Channel not initialized');
    }

    const content = Buffer.from(JSON.stringify(message));
    return this.channel.publish(exchange, routingKey, content, {
      persistent: true,
    });
  }

  async assertExchange(
    exchange: string,
    type: string,
    options?: amqp.Options.AssertExchange
  ): Promise<void> {
    if (!this.channel) {
      throw new Error('Channel not initialized');
    }
    await this.channel.assertExchange(exchange, type, options);
  }

  async bindQueue(queue: string, exchange: string, routingKey: string): Promise<void> {
    if (!this.channel) {
      throw new Error('Channel not initialized');
    }
    await this.channel.bindQueue(queue, exchange, routingKey);
  }

  async close(): Promise<void> {
    if (this.channel) {
      await this.channel.close();
    }
    if (this.connection) {
      await this.connection.close();
    }
  }
}

export const mqService = new MessageQueueService();
