-- 工厂智能化管理系统数据库设计

-- 用户表
CREATE TABLE `users` (
  `id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `username` VARCHAR(50) NOT NULL UNIQUE COMMENT '用户名',
  `password` VARCHAR(255) NOT NULL COMMENT '密码(bcrypt加密)',
  `real_name` VARCHAR(50) NOT NULL COMMENT '真实姓名',
  `email` VARCHAR(100) UNIQUE COMMENT '邮箱',
  `phone` VARCHAR(20) UNIQUE COMMENT '手机号',
  `avatar` VARCHAR(255) COMMENT '头像URL',
  `status` TINYINT DEFAULT 1 COMMENT '状态: 0-禁用 1-启用',
  `last_login_time` DATETIME COMMENT '最后登录时间',
  `last_login_ip` VARCHAR(50) COMMENT '最后登录IP',
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `deleted_at` DATETIME COMMENT '软删除时间',
  INDEX `idx_username` (`username`),
  INDEX `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户表';

-- 角色表
CREATE TABLE `roles` (
  `id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `name` VARCHAR(50) NOT NULL UNIQUE COMMENT '角色名称',
  `code` VARCHAR(50) NOT NULL UNIQUE COMMENT '角色编码',
  `description` VARCHAR(255) COMMENT '角色描述',
  `status` TINYINT DEFAULT 1 COMMENT '状态: 0-禁用 1-启用',
  `sort` INT DEFAULT 0 COMMENT '排序',
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX `idx_code` (`code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='角色表';

-- 权限表
CREATE TABLE `permissions` (
  `id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `parent_id` INT UNSIGNED DEFAULT 0 COMMENT '父级ID',
  `name` VARCHAR(50) NOT NULL COMMENT '权限名称',
  `code` VARCHAR(100) NOT NULL UNIQUE COMMENT '权限编码',
  `type` TINYINT NOT NULL COMMENT '类型: 1-菜单 2-按钮 3-接口',
  `path` VARCHAR(255) COMMENT '路由路径',
  `method` VARCHAR(10) COMMENT 'HTTP方法',
  `icon` VARCHAR(50) COMMENT '图标',
  `sort` INT DEFAULT 0 COMMENT '排序',
  `status` TINYINT DEFAULT 1 COMMENT '状态: 0-禁用 1-启用',
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX `idx_parent_id` (`parent_id`),
  INDEX `idx_code` (`code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='权限表';

-- 用户角色关联表
CREATE TABLE `user_roles` (
  `id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `user_id` INT UNSIGNED NOT NULL COMMENT '用户ID',
  `role_id` INT UNSIGNED NOT NULL COMMENT '角色ID',
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY `uk_user_role` (`user_id`, `role_id`),
  INDEX `idx_user_id` (`user_id`),
  INDEX `idx_role_id` (`role_id`),
  FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`role_id`) REFERENCES `roles`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户角色关联表';

-- 角色权限关联表
CREATE TABLE `role_permissions` (
  `id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `role_id` INT UNSIGNED NOT NULL COMMENT '角色ID',
  `permission_id` INT UNSIGNED NOT NULL COMMENT '权限ID',
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY `uk_role_permission` (`role_id`, `permission_id`),
  INDEX `idx_role_id` (`role_id`),
  INDEX `idx_permission_id` (`permission_id`),
  FOREIGN KEY (`role_id`) REFERENCES `roles`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`permission_id`) REFERENCES `permissions`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='角色权限关联表';

-- 操作日志表
CREATE TABLE `operation_logs` (
  `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `user_id` INT UNSIGNED COMMENT '用户ID',
  `username` VARCHAR(50) COMMENT '用户名',
  `module` VARCHAR(50) COMMENT '模块',
  `action` VARCHAR(50) COMMENT '操作',
  `method` VARCHAR(10) COMMENT 'HTTP方法',
  `path` VARCHAR(255) COMMENT '请求路径',
  `ip` VARCHAR(50) COMMENT 'IP地址',
  `user_agent` VARCHAR(500) COMMENT '用户代理',
  `request_data` TEXT COMMENT '请求数据',
  `response_data` TEXT COMMENT '响应数据',
  `status` TINYINT COMMENT '状态: 0-失败 1-成功',
  `error_msg` TEXT COMMENT '错误信息',
  `duration` INT COMMENT '耗时(ms)',
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX `idx_user_id` (`user_id`),
  INDEX `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='操作日志表';

CREATE TABLE `message_logs` (
  `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `source` VARCHAR(50) NOT NULL DEFAULT 'http_callback' COMMENT '消息来源',
  `instance_id` VARCHAR(100) DEFAULT '' COMMENT '实例ID或wxid',
  `room_id` VARCHAR(100) DEFAULT '' COMMENT '群聊ID',
  `room_name` VARCHAR(200) DEFAULT '' COMMENT '群聊名称',
  `sender_id` VARCHAR(100) DEFAULT '' COMMENT '发送人ID',
  `sender_name` VARCHAR(200) DEFAULT '' COMMENT '发送人名称',
  `message_type` VARCHAR(50) DEFAULT '' COMMENT '消息类型',
  `content_preview` TEXT NULL COMMENT '消息摘要',
  `payload_json` LONGTEXT NULL COMMENT '原始消息JSON',
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX `idx_source` (`source`),
  INDEX `idx_instance_id` (`instance_id`),
  INDEX `idx_room_id` (`room_id`),
  INDEX `idx_message_type` (`message_type`),
  INDEX `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='消息日志表';

-- 企微全局配置表
CREATE TABLE `wechat_config` (
  `id` INT UNSIGNED NOT NULL PRIMARY KEY,
  `host` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '企微API主机',
  `port` VARCHAR(50) NOT NULL DEFAULT '' COMMENT '企微API端口',
  `api_key` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '企微API密钥',
  `selected_wxid` VARCHAR(100) NOT NULL DEFAULT '' COMMENT '当前选中的wxid',
  `bound_instance_id` INT UNSIGNED NULL COMMENT '绑定实例ID',
  `bound_instance_name` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '绑定实例名称',
  `ws_path` VARCHAR(255) NOT NULL DEFAULT '/ws/wechat/messages' COMMENT '消息回调WebSocket路径',
  `http_path` VARCHAR(255) NOT NULL DEFAULT '/api/wechat/callback/http' COMMENT '消息回调HTTP路径',
  `callback_timeout` INT NOT NULL DEFAULT 5 COMMENT '回调超时时间(秒)'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='企微全局配置表';

-- 下游客户表
CREATE TABLE `downstream_customers` (
  `id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `customer_name` VARCHAR(100) NOT NULL COMMENT '客户名称',
  `contact_person` VARCHAR(100) DEFAULT '' COMMENT '联系人',
  `phone` VARCHAR(50) DEFAULT '' COMMENT '联系电话',
  `email` VARCHAR(100) DEFAULT '' COMMENT '邮箱',
  `company_name` VARCHAR(255) DEFAULT '' COMMENT '所属公司',
  `address` VARCHAR(255) DEFAULT '' COMMENT '地址',
  `remark` TEXT NULL COMMENT '备注',
  `erp_customer_id` VARCHAR(100) DEFAULT '' COMMENT 'ERP客户编号',
  `status` TINYINT NOT NULL DEFAULT 1 COMMENT '状态: 0-停用 1-启用',
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `deleted_at` DATETIME NULL,
  INDEX `idx_customer_name` (`customer_name`),
  INDEX `idx_status` (`status`),
  INDEX `idx_deleted_at` (`deleted_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='下游客户表';

-- 下游客户企微群映射表
CREATE TABLE `downstream_customer_wechat_rooms` (
  `id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `customer_id` INT UNSIGNED NOT NULL COMMENT '客户ID',
  `instance_id` INT UNSIGNED NULL COMMENT '企微实例ID',
  `room_id` VARCHAR(100) NOT NULL COMMENT '群聊ID',
  `room_name` VARCHAR(200) DEFAULT '' COMMENT '群聊名称',
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY `uk_customer_room` (`customer_id`, `room_id`),
  INDEX `idx_customer_id` (`customer_id`),
  INDEX `idx_room_id` (`room_id`),
  INDEX `idx_instance_id` (`instance_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='下游客户企微群映射表';

-- 下游客户订单待审核表
CREATE TABLE `downstream_order_reviews` (
  `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `source_type` VARCHAR(50) NOT NULL DEFAULT 'wechat' COMMENT '来源类型',
  `instance_id` INT UNSIGNED NULL COMMENT '企微实例ID',
  `room_id` VARCHAR(100) DEFAULT '' COMMENT '群聊ID',
  `room_name` VARCHAR(200) DEFAULT '' COMMENT '群聊名称',
  `sender_id` VARCHAR(100) DEFAULT '' COMMENT '发送人ID',
  `sender_name` VARCHAR(200) DEFAULT '' COMMENT '发送人名称',
  `message_type` VARCHAR(50) DEFAULT 'text' COMMENT '消息类型',
  `content_text` LONGTEXT NULL COMMENT '消息文本',
  `attachment_name` VARCHAR(255) DEFAULT '' COMMENT '附件名称',
  `attachment_url` VARCHAR(1000) DEFAULT '' COMMENT '附件地址',
  `attachment_mime` VARCHAR(100) DEFAULT '' COMMENT '附件MIME',
  `attachment_base64` LONGTEXT NULL COMMENT '附件Base64',
  `callback_payload` LONGTEXT NULL COMMENT '原始回调载荷',
  `parse_status` VARCHAR(50) NOT NULL DEFAULT 'pending' COMMENT '解析状态',
  `review_status` VARCHAR(50) NOT NULL DEFAULT 'pending' COMMENT '审核状态',
  `customer_id` INT UNSIGNED NULL COMMENT '匹配客户ID',
  `customer_name` VARCHAR(255) DEFAULT '' COMMENT '匹配客户名称',
  `ai_model` VARCHAR(100) DEFAULT '' COMMENT 'AI模型',
  `ai_error` TEXT NULL COMMENT 'AI解析错误',
  `parsed_order_json` LONGTEXT NULL COMMENT '解析后的订单JSON',
  `manual_order_json` LONGTEXT NULL COMMENT '手动录单JSON',
  `erp_order_no` VARCHAR(100) DEFAULT '' COMMENT 'ERP下单单号',
  `replaced_order_no` VARCHAR(255) DEFAULT '' COMMENT '被替换订单单号',
  `replace_source_ids` LONGTEXT NULL COMMENT '被取消未发货行JSON',
  `review_note` TEXT NULL COMMENT '审核备注',
  `reviewer_id` INT UNSIGNED NULL COMMENT '审核人ID',
  `reviewer_name` VARCHAR(100) DEFAULT '' COMMENT '审核人名称',
  `reviewed_at` DATETIME NULL COMMENT '审核时间',
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX `idx_room_id` (`room_id`),
  INDEX `idx_customer_id` (`customer_id`),
  INDEX `idx_parse_status` (`parse_status`),
  INDEX `idx_review_status` (`review_status`),
  INDEX `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='下游客户订单待审核表';

-- 初始化数据
INSERT INTO `roles` (`name`, `code`, `description`, `sort`) VALUES
('超级管理员', 'super_admin', '拥有系统所有权限', 1),
('管理员', 'admin', '拥有大部分管理权限', 2),
('普通用户', 'user', '基础用户权限', 3);

INSERT INTO `permissions` (`parent_id`, `name`, `code`, `type`, `path`, `icon`, `sort`) VALUES
(0, '系统管理', 'system', 1, '/system', 'setting', 1),
(1, '用户管理', 'system:user', 1, '/system/user', 'user', 1),
(2, '用户列表', 'system:user:list', 2, NULL, NULL, 1),
(2, '新增用户', 'system:user:add', 2, NULL, NULL, 2),
(2, '编辑用户', 'system:user:edit', 2, NULL, NULL, 3),
(2, '删除用户', 'system:user:delete', 2, NULL, NULL, 4),
(1, '角色管理', 'system:role', 1, '/system/role', 'team', 2),
(7, '角色列表', 'system:role:list', 2, NULL, NULL, 1),
(7, '新增角色', 'system:role:add', 2, NULL, NULL, 2),
(7, '编辑角色', 'system:role:edit', 2, NULL, NULL, 3),
(7, '删除角色', 'system:role:delete', 2, NULL, NULL, 4),
(1, '权限管理', 'system:permission', 1, '/system/permission', 'lock', 3);

-- 默认管理员账号 (密码: admin123)
INSERT INTO `users` (`username`, `password`, `real_name`, `email`, `status`) VALUES
('admin', '$2b$12$adLFAMdvEOCJn088zaTh8u4kVIQhSQoKUtHwQ0865jHGP7sozJKW6', '系统管理员', 'admin@example.com', 1);

INSERT INTO `wechat_config` (`id`, `host`, `port`, `api_key`, `selected_wxid`, `bound_instance_id`, `bound_instance_name`, `ws_path`, `http_path`, `callback_timeout`) VALUES
(1, '', '', '', '', NULL, '', '/ws/wechat/messages', '/api/wechat/callback/http', 5);

INSERT INTO `user_roles` (`user_id`, `role_id`) VALUES (1, 1);

-- 超级管理员拥有所有权限
INSERT INTO `role_permissions` (`role_id`, `permission_id`) VALUES
(1, 1), (1, 2), (1, 3), (1, 4), (1, 5), (1, 6), (1, 7), (1, 8), (1, 9), (1, 10), (1, 11), (1, 12);

-- 管理员拥有用户管理与角色查看权限
INSERT INTO `role_permissions` (`role_id`, `permission_id`) VALUES
(2, 1), (2, 2), (2, 3), (2, 4), (2, 5), (2, 6), (2, 7), (2, 8);
