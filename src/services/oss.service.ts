import OSS from 'ali-oss';
import { config } from '../config';

class OSSService {
  private client: OSS;

  constructor() {
    this.client = new OSS({
      region: config.oss.region,
      accessKeyId: config.oss.accessKeyId,
      accessKeySecret: config.oss.accessKeySecret,
      bucket: config.oss.bucket,
    });
  }

  async uploadFile(fileName: string, fileBuffer: Buffer): Promise<string> {
    try {
      const result = await this.client.put(fileName, fileBuffer);
      return (result as any).url || result.name;
    } catch (error) {
      throw new Error('文件上传失败');
    }
  }

  async uploadStream(fileName: string, stream: any): Promise<string> {
    try {
      const result = await this.client.putStream(fileName, stream);
      return (result as any).url || result.name;
    } catch (error) {
      throw new Error('文件上传失败');
    }
  }

  async deleteFile(fileName: string): Promise<void> {
    try {
      await this.client.delete(fileName);
    } catch (error) {
      throw new Error('文件删除失败');
    }
  }

  async getFileUrl(fileName: string, expires: number = 3600): Promise<string> {
    try {
      const url = this.client.signatureUrl(fileName);
      return url;
    } catch (error) {
      throw new Error('获取文件URL失败');
    }
  }

  async listFiles(prefix?: string, maxKeys: number = 100): Promise<any[]> {
    try {
      const result = await this.client.list({
        prefix,
        'max-keys': maxKeys,
      } as any, {});
      return result.objects || [];
    } catch (error) {
      throw new Error('获取文件列表失败');
    }
  }
}

export const ossService = new OSSService();
