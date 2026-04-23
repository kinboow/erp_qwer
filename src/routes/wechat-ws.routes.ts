import { Router } from 'express';
import { WechatWsController } from '../controllers/wechat-ws.controller';

const router = Router();
const wechatWsController = new WechatWsController();

router.get('/status', (req, res) => wechatWsController.getStatus(req, res));
router.post('/connect', (req, res) => wechatWsController.connect(req, res));
router.delete('/connect/:instanceId', (req, res) => wechatWsController.disconnect(req, res));

export default router;
