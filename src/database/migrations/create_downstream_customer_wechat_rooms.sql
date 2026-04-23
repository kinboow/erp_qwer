CREATE TABLE IF NOT EXISTS `downstream_customer_wechat_rooms` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `customer_id` INT UNSIGNED NOT NULL COMMENT '客户ID',
  `instance_id` INT UNSIGNED NOT NULL COMMENT '企微实例ID',
  `room_id` VARCHAR(128) NOT NULL DEFAULT '' COMMENT '群ID',
  `room_name` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '群名称',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uniq_customer_room` (`customer_id`, `instance_id`, `room_id`),
  KEY `idx_customer_id` (`customer_id`),
  KEY `idx_instance_id` (`instance_id`),
  KEY `idx_room_id` (`room_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='下游客户关联企微群表';
