import { db } from '../database';

interface CustomerWechatRoomDto {
  instance_id: number;
  room_id: string;
  room_name: string;
}

export interface CreateCustomerDto {
  customer_name: string;
  contact_person?: string;
  phone?: string;
  email?: string;
  company_name?: string;
  address?: string;
  remark?: string;
  status?: number;
  wechat_rooms?: CustomerWechatRoomDto[];
}

export interface UpdateCustomerDto {
  customer_name?: string;
  contact_person?: string;
  phone?: string;
  email?: string;
  company_name?: string;
  address?: string;
  remark?: string;
  status?: number;
  wechat_rooms?: CustomerWechatRoomDto[];
}

export class CustomerService {
  async getCustomerList(page: number = 1, pageSize: number = 10, keyword?: string) {
    const offset = (page - 1) * pageSize;

    let sql = `
      SELECT id, customer_name, contact_person, phone, email, company_name, address, remark, status, created_at, updated_at
      FROM downstream_customers
      WHERE deleted_at IS NULL
    `;
    const params: any[] = [];

    if (keyword) {
      const searchTerm = `%${keyword}%`;
      sql += ' AND (customer_name LIKE ? OR contact_person LIKE ? OR phone LIKE ? OR company_name LIKE ?)';
      params.push(searchTerm, searchTerm, searchTerm, searchTerm);
    }

    sql += ' ORDER BY created_at DESC LIMIT ? OFFSET ?';
    params.push(pageSize, offset);

    const list = await db.query(sql, params);

    let countSql = 'SELECT COUNT(*) as total FROM downstream_customers WHERE deleted_at IS NULL';
    const countParams: any[] = [];
    if (keyword) {
      const searchTerm = `%${keyword}%`;
      countSql += ' AND (customer_name LIKE ? OR contact_person LIKE ? OR phone LIKE ? OR company_name LIKE ?)';
      countParams.push(searchTerm, searchTerm, searchTerm, searchTerm);
    }

    const countRows = await db.query(countSql, countParams);
    const total = countRows[0]?.total || 0;

    const customerIds = list.map((item: any) => item.id);
    const roomMap = await this.getWechatRoomsMap(customerIds);

    return {
      list: list.map((item: any) => ({
        ...item,
        wechat_rooms: roomMap.get(item.id) || []
      })),
      total,
      page,
      pageSize
    };
  }

  async getCustomerById(id: number) {
    const rows = await db.query(
      'SELECT id, customer_name, contact_person, phone, email, company_name, address, remark, status, created_at, updated_at FROM downstream_customers WHERE id = ? AND deleted_at IS NULL',
      [id]
    );

    if (!rows.length) {
      throw new Error('客户不存在');
    }

    const wechatRooms = await this.getCustomerWechatRooms(id);

    return {
      ...rows[0],
      wechat_rooms: wechatRooms
    };
  }

  async createCustomer(data: CreateCustomerDto) {
    const {
      customer_name,
      contact_person,
      phone,
      email,
      company_name,
      address,
      remark,
      status = 1,
      wechat_rooms = [],
    } = data;

    if (!customer_name) {
      throw new Error('客户名称不能为空');
    }

    return await db.transaction(async (conn: any) => {
      const [result]: any = await conn.execute(
        'INSERT INTO downstream_customers (customer_name, contact_person, phone, email, company_name, address, remark, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        [customer_name, contact_person || '', phone || '', email || '', company_name || '', address || '', remark || '', status]
      );

      const customerId = result.insertId;
      await this.replaceCustomerWechatRooms(conn, customerId, wechat_rooms);

      return { id: customerId, customer_name };
    });
  }

  async updateCustomer(id: number, data: UpdateCustomerDto) {
    const { wechat_rooms, ...baseData } = data;

    return await db.transaction(async (conn: any) => {
      const updates: string[] = [];
      const params: any[] = [];

      Object.entries(baseData).forEach(([key, value]) => {
        if (value !== undefined) {
          updates.push(`${key} = ?`);
          params.push(value);
        }
      });

      if (updates.length) {
        params.push(id);
        await conn.execute(
          `UPDATE downstream_customers SET ${updates.join(', ')}, updated_at = NOW() WHERE id = ? AND deleted_at IS NULL`,
          params
        );
      }

      if (wechat_rooms !== undefined) {
        await this.replaceCustomerWechatRooms(conn, id, wechat_rooms);
      }
    });
  }

  async deleteCustomer(id: number) {
    await db.transaction(async (conn: any) => {
      await conn.execute('UPDATE downstream_customers SET deleted_at = NOW() WHERE id = ?', [id]);
      await conn.execute('DELETE FROM downstream_customer_wechat_rooms WHERE customer_id = ?', [id]);
    });
  }

  private async getWechatRoomsMap(customerIds: number[]) {
    const map = new Map<number, CustomerWechatRoomDto[]>();

    if (!customerIds.length) {
      return map;
    }

    const placeholders = customerIds.map(() => '?').join(', ');
    const rows = await db.query(
      `SELECT customer_id, instance_id, room_id, room_name FROM downstream_customer_wechat_rooms WHERE customer_id IN (${placeholders}) ORDER BY id ASC`,
      customerIds
    );

    rows.forEach((row: any) => {
      if (!map.has(row.customer_id)) {
        map.set(row.customer_id, []);
      }
      map.get(row.customer_id)?.push({
        instance_id: row.instance_id,
        room_id: row.room_id,
        room_name: row.room_name
      });
    });

    return map;
  }

  private async getCustomerWechatRooms(customerId: number) {
    const rows = await db.query(
      'SELECT instance_id, room_id, room_name FROM downstream_customer_wechat_rooms WHERE customer_id = ? ORDER BY id ASC',
      [customerId]
    );

    return rows.map((row: any) => ({
      instance_id: row.instance_id,
      room_id: row.room_id,
      room_name: row.room_name
    }));
  }

  private async replaceCustomerWechatRooms(conn: any, customerId: number, rooms: CustomerWechatRoomDto[]) {
    await conn.execute('DELETE FROM downstream_customer_wechat_rooms WHERE customer_id = ?', [customerId]);

    if (!rooms?.length) {
      return;
    }

    for (const room of rooms) {
      if (!room?.instance_id || !room?.room_id) {
        continue;
      }

      await conn.execute(
        'INSERT INTO downstream_customer_wechat_rooms (customer_id, instance_id, room_id, room_name) VALUES (?, ?, ?, ?)',
        [customerId, room.instance_id, room.room_id, room.room_name || '']
      );
    }
  }
}
