import { Request, Response } from 'express';
import { CustomerService } from '../services/customer.service';

const customerService = new CustomerService();

export class CustomerController {
  async getList(req: Request, res: Response) {
    try {
      const { page = 1, pageSize = 10, keyword } = req.query;
      const result = await customerService.getCustomerList(
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
      const result = await customerService.getCustomerById(Number(id));
      res.json({
        code: 200,
        message: '获取成功',
        data: result,
      });
    } catch (error: any) {
      res.status(400).json({ code: 400, message: error.message });
    }
  }

  async create(req: Request, res: Response) {
    try {
      const result = await customerService.createCustomer(req.body);
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
      await customerService.updateCustomer(Number(id), req.body);
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
      await customerService.deleteCustomer(Number(id));
      res.json({
        code: 200,
        message: '删除成功',
      });
    } catch (error: any) {
      res.status(400).json({ code: 400, message: error.message });
    }
  }
}
