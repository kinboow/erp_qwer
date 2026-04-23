CREATE TABLE IF NOT EXISTS `operation_logs` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `user_id` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '操作人ID',
  `username` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '操作人用户名',
  `module` VARCHAR(32) NOT NULL DEFAULT '' COMMENT '功能模块: user, role, wechat, auth',
  `action` VARCHAR(32) NOT NULL DEFAULT '' COMMENT '操作类型: create, update, delete, login, logout',
  `description` VARCHAR(500) NOT NULL DEFAULT '' COMMENT '操作描述',
  `ip` VARCHAR(64) NOT NULL DEFAULT '' COMMENT 'IP地址',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '操作时间',
  PRIMARY KEY (`id`),
  INDEX `idx_module` (`module`),
  INDEX `idx_action` (`action`),
  INDEX `idx_user_id` (`user_id`),
  INDEX `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='操作日志表';
