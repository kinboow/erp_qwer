import { Router } from 'express';
import { CustomerController } from '../controllers/customer.controller';
import { authMiddleware } from '../middlewares/auth.middleware';

const router = Router();
const customerController = new CustomerController();

router.use(authMiddleware);

router.get('/', (req, res) => customerController.getList(req, res));
router.get('/:id', (req, res) => customerController.getById(req, res));
router.post('/', (req, res) => customerController.create(req, res));
router.put('/:id', (req, res) => customerController.update(req, res));
router.delete('/:id', (req, res) => customerController.delete(req, res));

export default router;
