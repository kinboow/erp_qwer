import { Router } from 'express';
import { UserController } from '../controllers/user.controller';
import { authMiddleware } from '../middlewares/auth.middleware';
import { permissionMiddleware } from '../middlewares/permission.middleware';

const router = Router();
const userController = new UserController();

// 所有路由都需要认证
router.use(authMiddleware);

// 获取用户列表
router.get('/', permissionMiddleware('system:user:list'), (req, res) =>
  userController.getList(req, res)
);

// 获取用户详情
router.get('/:id', permissionMiddleware('system:user:list'), (req, res) =>
  userController.getById(req, res)
);

// 创建用户
router.post('/', permissionMiddleware('system:user:add'), (req, res) =>
  userController.create(req, res)
);

// 更新用户
router.put('/:id', permissionMiddleware('system:user:edit'), (req, res) =>
  userController.update(req, res)
);

// 删除用户
router.delete('/:id', permissionMiddleware('system:user:delete'), (req, res) =>
  userController.delete(req, res)
);

// 重置密码
router.post('/:id/reset-password', permissionMiddleware('system:user:edit'), (req, res) =>
  userController.resetPassword(req, res)
);

export default router;
