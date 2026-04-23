CREATE TABLE IF NOT EXISTS `downstream_customers` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `customer_name` VARCHAR(120) NOT NULL DEFAULT '' COMMENT '客户名称',
  `contact_person` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '联系人',
  `phone` VARCHAR(32) NOT NULL DEFAULT '' COMMENT '联系电话',
  `email` VARCHAR(120) NOT NULL DEFAULT '' COMMENT '邮箱',
  `company_name` VARCHAR(160) NOT NULL DEFAULT '' COMMENT '公司名称',
  `address` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '地址',
  `remark` VARCHAR(500) NOT NULL DEFAULT '' COMMENT '备注',
  `status` TINYINT NOT NULL DEFAULT 1 COMMENT '状态 1启用 0停用',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `deleted_at` DATETIME NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  INDEX `idx_customer_name` (`customer_name`),
  INDEX `idx_contact_person` (`contact_person`),
  INDEX `idx_phone` (`phone`),
  INDEX `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='下游客户表';
