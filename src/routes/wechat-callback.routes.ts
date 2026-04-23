import { Router } from 'express';
import { WechatCallbackController } from '../controllers/wechat-callback.controller';

const router = Router();
const wechatCallbackController = new WechatCallbackController();

router.post('/http', (req, res) => wechatCallbackController.receiveHttpMessage(req, res));
router.get('/http', (req, res) => wechatCallbackController.receiveHttpMessage(req, res));

export default router;
