import { db } from '../database';
import { redis } from '../utils/redis';

export interface CreateRoleDto {
  name: string;
  code: string;
  description?: string;
  sort?: number;
  permissionIds?: number[];
}

export interface UpdateRoleDto {
  name?: string;
  description?: string;
  status?: number;
  sort?: number;
  permissionIds?: number[];
}

export class RoleService {
  async getRoleList(page: number = 1, pageSize: number = 10, keyword?: string) {
    const offset = (page - 1) * pageSize;

    let sql = `
      SELECT r.id, r.name, r.code, r.description, r.status, r.sort, r.created_at,
             COUNT(DISTINCT ur.user_id) as user_count
      FROM roles r
      LEFT JOIN user_roles ur ON r.id = ur.role_id
      WHERE 1=1
    `;
    const params: any[] = [];

    if (keyword) {
      sql += ' AND (r.name LIKE ? OR r.code LIKE ?)';
      const searchTerm = `%${keyword}%`;
      params.push(searchTerm, searchTerm);
    }

    sql += ' GROUP BY r.id ORDER BY r.sort ASC, r.created_at ASC LIMIT ? OFFSET ?';
    params.push(pageSize, offset);

    const roles = await db.query(sql, params);

    let countSql = 'SELECT COUNT(*) as total FROM roles WHERE 1=1';
    const countParams: any[] = [];
    if (keyword) {
      countSql += ' AND (name LIKE ? OR code LIKE ?)';
      const searchTerm = `%${keyword}%`;
      countParams.push(searchTerm, searchTerm);
    }
    const countResult = await db.query(countSql, countParams);
    const total = countResult[0].total;

    return { list: roles, total, page, pageSize };
  }

  async getAllRoles() {
    const sql = `SELECT id, name, code, description, status FROM roles WHERE status = 1 ORDER BY sort ASC`;
    return await db.query(sql);
  }

  async getRoleById(id: number) {
    const sql = `SELECT * FROM roles WHERE id = ?`;
    const roles = await db.query(sql, [id]);
    if (roles.length === 0) {
      throw new Error('角色不存在');
    }

    // 获取角色关联的权限ID
    const permSql = `SELECT permission_id FROM role_permissions WHERE role_id = ?`;
    const perms = await db.query(permSql, [id]);
    const permissionIds = perms.map((p: any) => p.permission_id);

    return { ...roles[0], permissionIds };
  }

  async createRole(data: CreateRoleDto) {
    const { name, code, description, sort, permissionIds } = data;

    const existing = await db.query('SELECT id FROM roles WHERE code = ?', [code]);
    if (existing.length > 0) {
      throw new Error('角色编码已存在');
    }

    return await db.transaction(async (conn: any) => {
      const [result]: any = await conn.execute(
        'INSERT INTO roles (name, code, description, sort) VALUES (?, ?, ?, ?)',
        [name, code, description || '', sort || 0]
      );
      const roleId = result.insertId;

      if (permissionIds && permissionIds.length > 0) {
        for (const permId of permissionIds) {
          await conn.execute(
            'INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)',
            [roleId, permId]
          );
        }
      }

      return { id: roleId, name, code };
    });
  }

  async updateRole(id: number, data: UpdateRoleDto) {
    const { name, description, status, sort, permissionIds } = data;

    return await db.transaction(async (conn: any) => {
      const updates: string[] = [];
      const params: any[] = [];

      if (name !== undefined) { updates.push('name = ?'); params.push(name); }
      if (description !== undefined) { updates.push('description = ?'); params.push(description); }
      if (status !== undefined) { updates.push('status = ?'); params.push(status); }
      if (sort !== undefined) { updates.push('sort = ?'); params.push(sort); }

      if (updates.length > 0) {
        params.push(id);
        await conn.execute(`UPDATE roles SET ${updates.join(', ')} WHERE id = ?`, params);
      }

      if (permissionIds !== undefined) {
        await conn.execute('DELETE FROM role_permissions WHERE role_id = ?', [id]);
        if (permissionIds.length > 0) {
          for (const permId of permissionIds) {
            await conn.execute(
              'INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)',
              [id, permId]
            );
          }
        }
      }

      // 清除所有拥有该角色用户的权限缓存
      const users = await conn.execute(
        'SELECT user_id FROM user_roles WHERE role_id = ?', [id]
      );
      const userRows = users[0] || users;
      for (const u of userRows) {
        await redis.del(`user:permissions:${u.user_id}`);
      }
    });
  }

  async deleteRole(id: number) {
    // 不允许删除超级管理员角色
    const role = await db.query('SELECT code FROM roles WHERE id = ?', [id]);
    if (role.length > 0 && role[0].code === 'super_admin') {
      throw new Error('不能删除超级管理员角色');
    }

    return await db.transaction(async (conn: any) => {
      // 清除关联用户的缓存
      const users = await conn.execute(
        'SELECT user_id FROM user_roles WHERE role_id = ?', [id]
      );
      const userRows = users[0] || users;
      for (const u of userRows) {
        await redis.del(`user:permissions:${u.user_id}`);
      }

      await conn.execute('DELETE FROM role_permissions WHERE role_id = ?', [id]);
      await conn.execute('DELETE FROM user_roles WHERE role_id = ?', [id]);
      await conn.execute('DELETE FROM roles WHERE id = ?', [id]);
    });
  }

  async getAllPermissions() {
    const sql = `SELECT id, parent_id, name, code, type, path, icon, sort, status FROM permissions ORDER BY sort ASC`;
    const permissions = await db.query(sql);

    // 构建树形结构
    return this.buildPermissionTree(permissions);
  }

  private buildPermissionTree(permissions: any[], parentId: number = 0): any[] {
    return permissions
      .filter((p: any) => p.parent_id === parentId)
      .map((p: any) => ({
        ...p,
        children: this.buildPermissionTree(permissions, p.id)
      }));
  }
}
