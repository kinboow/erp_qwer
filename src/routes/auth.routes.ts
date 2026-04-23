import { Router } from 'express';
import { AuthController } from '../controllers/auth.controller';
import { authMiddleware } from '../middlewares/auth.middleware';

const router = Router();
const authController = new AuthController();

// 登录
router.post('/login', (req, res) => authController.login(req, res));

// 注册
router.post('/register', (req, res) => authController.register(req, res));

// 退出登录
router.post('/logout', authMiddleware, (req, res) => authController.logout(req, res));

// 刷新token
router.post('/refresh', (req, res) => authController.refreshToken(req, res));

// 获取用户信息
router.get('/userinfo', authMiddleware, (req, res) => authController.getUserInfo(req, res));

export default router;
