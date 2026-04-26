-- 企业微信全局配置表（单行配置）
CREATE TABLE IF NOT EXISTS `wechat_config` (
  `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `host` VARCHAR(255) NOT NULL DEFAULT '' COMMENT 'API 服务器地址',
  `port` VARCHAR(10) NOT NULL DEFAULT '' COMMENT 'API 端口',
  `api_key` VARCHAR(255) DEFAULT '' COMMENT 'API 密钥 (X-API-Key)',
  `selected_wxid` VARCHAR(100) DEFAULT '' COMMENT '当前选中的实例 wxid',
  `ws_path` VARCHAR(255) DEFAULT '/ws/wechat/messages' COMMENT 'WS 回调路径',
  `http_path` VARCHAR(255) DEFAULT '/api/wechat/callback/http' COMMENT 'HTTP 回调路径',
  `callback_timeout` INT DEFAULT 5 COMMENT '回调超时(秒)',
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='企业微信全局配置';

-- 插入默认空行
INSERT INTO `wechat_config` (`id`, `host`, `port`) VALUES (1, '', '')
  ON DUPLICATE KEY UPDATE `id` = `id`;
