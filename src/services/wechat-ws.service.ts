import WebSocket from 'ws';
import { logger } from '../utils/logger';

interface ConnectionMeta {
  instanceId: string;
  url: string;
  socket: WebSocket;
  reconnectTimer?: NodeJS.Timeout;
  manuallyClosed: boolean;
}

class WechatWsService {
  private connections = new Map<string, ConnectionMeta>();

  connect(instanceId: string, url: string) {
    if (!instanceId) {
      throw new Error('instanceId 不能为空');
    }
    if (!url) {
      throw new Error('WebSocket 地址不能为空');
    }

    const existing = this.connections.get(instanceId);
    if (existing) {
      if (existing.url === url && existing.socket.readyState === WebSocket.OPEN) {
        return { instanceId, url, status: 'connected' };
      }
      this.disconnect(instanceId);
    }

    const socket = new WebSocket(url);
    const meta: ConnectionMeta = {
      instanceId,
      url,
      socket,
      manuallyClosed: false,
    };
    this.connections.set(instanceId, meta);

    socket.on('open', () => {
      logger.info('WeChat WS client connected', { instanceId, url });
    });

    socket.on('message', async (data: WebSocket.RawData) => {
      const payload = typeof data === 'string' ? data : data.toString();
      logger.info('WeChat WS message received', {
        instanceId,
        payload,
      });
    });

    socket.on('close', (code: number, reason: Buffer) => {
      const reasonText = typeof reason === 'string' ? reason : reason?.toString?.() || '';
      logger.warn('WeChat WS client disconnected', {
        instanceId,
        url,
        code,
        reason: reasonText,
      });

      if (!meta.manuallyClosed) {
        this.scheduleReconnect(instanceId, url);
      }
    });

    socket.on('error', (error: Error) => {
      logger.error('WeChat WS client error', {
        instanceId,
        url,
        error: error instanceof Error ? error.message : String(error),
      });
    });

    return { instanceId, url, status: 'connecting' };
  }

  disconnect(instanceId: string) {
    const meta = this.connections.get(instanceId);
    if (!meta) {
      return false;
    }

    meta.manuallyClosed = true;
    if (meta.reconnectTimer) {
      clearTimeout(meta.reconnectTimer);
    }
    meta.socket.close();
    this.connections.delete(instanceId);
    logger.info('WeChat WS client manually disconnected', { instanceId, url: meta.url });
    return true;
  }

  getStatus(instanceId?: string) {
    if (instanceId) {
      const meta = this.connections.get(instanceId);
      if (!meta) {
        return null;
      }
      return this.serialize(meta);
    }

    return Array.from(this.connections.values()).map((meta) => this.serialize(meta));
  }

  async closeAll() {
    const ids = Array.from(this.connections.keys());
    ids.forEach((id) => this.disconnect(id));
  }

  private scheduleReconnect(instanceId: string, url: string) {
    const current = this.connections.get(instanceId);
    if (!current || current.manuallyClosed) {
      return;
    }

    if (current.reconnectTimer) {
      clearTimeout(current.reconnectTimer);
    }

    current.reconnectTimer = setTimeout(() => {
      if (!this.connections.get(instanceId)?.manuallyClosed) {
        logger.info('Reconnecting WeChat WS client', { instanceId, url });
        this.connect(instanceId, url);
      }
    }, 5000);
  }

  private serialize(meta: ConnectionMeta) {
    const stateMap: Record<number, string> = {
      [WebSocket.CONNECTING]: 'connecting',
      [WebSocket.OPEN]: 'open',
      [WebSocket.CLOSING]: 'closing',
      [WebSocket.CLOSED]: 'closed',
    };

    return {
      instanceId: meta.instanceId,
      url: meta.url,
      readyState: stateMap[meta.socket.readyState] || 'unknown',
    };
  }
}

export const wechatWsService = new WechatWsService();
