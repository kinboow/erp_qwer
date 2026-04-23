import { Request, Response } from 'express';
import { UserService } from '../services/user.service';

const userService = new UserService();

export class UserController {
  async getList(req: Request, res: Response) {
    try {
      const { page = 1, pageSize = 10, keyword } = req.query;
      const result = await userService.getUserList(
        Number(page),
        Number(pageSize),
        keyword as string
      );

      res.json({
        code: 200,
        message: '获取成功',
        data: result,
      });
    } catch (error: any) {
      res.status(400).json({ code: 400, message: error.message });
    }
  }

  async getById(req: Request, res: Response) {
    try {
      const { id } = req.params;
      const user = await userService.getUserById(Number(id));

      res.json({
        code: 200,
        message: '获取成功',
        data: user,
      });
    } catch (error: any) {
      res.status(400).json({ code: 400, message: error.message });
    }
  }

  async create(req: Request, res: Response) {
    try {
      const result = await userService.createUser(req.body);

      res.json({
        code: 200,
        message: '创建成功',
        data: result,
      });
    } catch (error: any) {
      res.status(400).json({ code: 400, message: error.message });
    }
  }

  async update(req: Request, res: Response) {
    try {
      const { id } = req.params;
      await userService.updateUser(Number(id), req.body);

      res.json({
        code: 200,
        message: '更新成功',
      });
    } catch (error: any) {
      res.status(400).json({ code: 400, message: error.message });
    }
  }

  async delete(req: Request, res: Response) {
    try {
      const { id } = req.params;
      await userService.deleteUser(Number(id));

      res.json({
        code: 200,
        message: '删除成功',
      });
    } catch (error: any) {
      res.status(400).json({ code: 400, message: error.message });
    }
  }

  async resetPassword(req: Request, res: Response) {
    try {
      const { id } = req.params;
      const { newPassword } = req.body;

      if (!newPassword) {
        return res.status(400).json({ code: 400, message: '新密码不能为空' });
      }

      await userService.resetPassword(Number(id), newPassword);

      res.json({
        code: 200,
        message: '密码重置成功',
      });
    } catch (error: any) {
      res.status(400).json({ code: 400, message: error.message });
    }
  }
}
