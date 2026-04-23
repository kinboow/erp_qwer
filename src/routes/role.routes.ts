import { Router } from 'express';
import { RoleController } from '../controllers/role.controller';
import { authMiddleware } from '../middlewares/auth.middleware';
import { permissionMiddleware } from '../middlewares/permission.middleware';

const router = Router();
const roleController = new RoleController();

// 所有路由都需要认证
router.use(authMiddleware);

// 获取所有权限树（用于角色分配权限）
router.get('/permissions', permissionMiddleware('system:role:list'), (req, res) =>
  roleController.getPermissions(req, res)
);

// 获取所有角色（下拉列表用）
router.get('/all', permissionMiddleware('system:role:list'), (req, res) =>
  roleController.getAll(req, res)
);

// 获取角色列表（分页）
router.get('/', permissionMiddleware('system:role:list'), (req, res) =>
  roleController.getList(req, res)
);

// 获取角色详情
router.get('/:id', permissionMiddleware('system:role:list'), (req, res) =>
  roleController.getById(req, res)
);

// 创建角色
router.post('/', permissionMiddleware('system:role:add'), (req, res) =>
  roleController.create(req, res)
);

// 更新角色
router.put('/:id', permissionMiddleware('system:role:edit'), (req, res) =>
  roleController.update(req, res)
);

// 删除角色
router.delete('/:id', permissionMiddleware('system:role:delete'), (req, res) =>
  roleController.delete(req, res)
);

export default router;
