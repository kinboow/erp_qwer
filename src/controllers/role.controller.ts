import { Response } from 'express';
import { AuthRequest } from '../middlewares/auth.middleware';
import { RoleService } from '../services/role.service';

const roleService = new RoleService();

export class RoleController {
  async getList(req: AuthRequest, res: Response) {
    try {
      const { page = 1, page_size = 10, keyword } = req.query;
      const result = await roleService.getRoleList(
        Number(page), Number(page_size), keyword as string
      );
      res.json({ code: 200, data: result });
    } catch (error: any) {
      res.status(500).json({ code: 500, message: error.message });
    }
  }

  async getAll(req: AuthRequest, res: Response) {
    try {
      const roles = await roleService.getAllRoles();
      res.json({ code: 200, data: roles });
    } catch (error: any) {
      res.status(500).json({ code: 500, message: error.message });
    }
  }

  async getById(req: AuthRequest, res: Response) {
    try {
      const role = await roleService.getRoleById(Number(req.params.id));
      res.json({ code: 200, data: role });
    } catch (error: any) {
      res.status(404).json({ code: 404, message: error.message });
    }
  }

  async create(req: AuthRequest, res: Response) {
    try {
      const result = await roleService.createRole(req.body);
      res.json({ code: 200, data: result, message: '创建成功' });
    } catch (error: any) {
      res.status(400).json({ code: 400, message: error.message });
    }
  }

  async update(req: AuthRequest, res: Response) {
    try {
      await roleService.updateRole(Number(req.params.id), req.body);
      res.json({ code: 200, message: '更新成功' });
    } catch (error: any) {
      res.status(400).json({ code: 400, message: error.message });
    }
  }

  async delete(req: AuthRequest, res: Response) {
    try {
      await roleService.deleteRole(Number(req.params.id));
      res.json({ code: 200, message: '删除成功' });
    } catch (error: any) {
      res.status(400).json({ code: 400, message: error.message });
    }
  }

  async getPermissions(req: AuthRequest, res: Response) {
    try {
      const permissions = await roleService.getAllPermissions();
      res.json({ code: 200, data: permissions });
    } catch (error: any) {
      res.status(500).json({ code: 500, message: error.message });
    }
  }
}
