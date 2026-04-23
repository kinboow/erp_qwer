-- 企业微信群聊监听配置数据库设计

-- 企业微信实例表
CREATE TABLE `wechat_instances` (
  `id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `wxid` VARCHAR(100) NOT NULL UNIQUE COMMENT '企业微信实例ID',
  `name` VARCHAR(100) NOT NULL COMMENT '实例名称',
  `status` TINYINT DEFAULT 1 COMMENT '状态: 0-离线 1-在线',
  `api_base_url` VARCHAR(255) NOT NULL COMMENT 'API基础URL',
  `api_key` VARCHAR(255) COMMENT 'API调用密钥(X-API-Key)',
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX `idx_wxid` (`wxid`),
  INDEX `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='企业微信实例表';

-- 群聊监听配置表
CREATE TABLE `wechat_room_listeners` (
  `id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `instance_id` INT UNSIGNED NOT NULL COMMENT '企业微信实例ID',
  `room_id` VARCHAR(100) NOT NULL COMMENT '群聊ID',
  `room_name` VARCHAR(200) COMMENT '群聊名称',
  `is_enabled` TINYINT DEFAULT 1 COMMENT '是否启用监听: 0-禁用 1-启用',
  `description` VARCHAR(500) COMMENT '备注说明',
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY `uk_instance_room` (`instance_id`, `room_id`),
  INDEX `idx_instance_id` (`instance_id`),
  INDEX `idx_is_enabled` (`is_enabled`),
  FOREIGN KEY (`instance_id`) REFERENCES `wechat_instances`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='群聊监听配置表';
