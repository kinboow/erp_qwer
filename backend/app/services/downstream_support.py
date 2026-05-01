import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _add_column_if_not_exists(db: Session, table: str, column: str, definition: str):
    """Safely add a column if it doesn't already exist."""
    try:
        row = db.execute(text(
            "SELECT COUNT(*) AS cnt FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = :table AND column_name = :col"
        ), {"table": table, "col": column}).scalar()
        if not row:
            db.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))
    except Exception as e:
        logger.debug("add column %s.%s skipped: %s", table, column, e)


def ensure_downstream_support_tables(db: Session):
    db.execute(text(
        "CREATE TABLE IF NOT EXISTS downstream_customers ("
        "id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, "
        "customer_name VARCHAR(100) NOT NULL, "
        "contact_person VARCHAR(100) DEFAULT '', "
        "phone VARCHAR(50) DEFAULT '', "
        "email VARCHAR(100) DEFAULT '', "
        "company_name VARCHAR(255) DEFAULT '', "
        "address VARCHAR(255) DEFAULT '', "
        "remark TEXT NULL, "
        "erp_customer_id VARCHAR(100) DEFAULT '', "
        "status TINYINT NOT NULL DEFAULT 1, "
        "created_at DATETIME DEFAULT CURRENT_TIMESTAMP, "
        "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP, "
        "deleted_at DATETIME NULL, "
        "INDEX idx_customer_name (customer_name), "
        "INDEX idx_status (status), "
        "INDEX idx_deleted_at (deleted_at)"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
    ))
    db.execute(text(
        "CREATE TABLE IF NOT EXISTS downstream_customer_wechat_rooms ("
        "id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, "
        "customer_id INT UNSIGNED NOT NULL, "
        "instance_id INT UNSIGNED NULL, "
        "room_id VARCHAR(100) NOT NULL, "
        "room_name VARCHAR(200) DEFAULT '', "
        "created_at DATETIME DEFAULT CURRENT_TIMESTAMP, "
        "UNIQUE KEY uk_customer_room (customer_id, room_id), "
        "INDEX idx_customer_id (customer_id), "
        "INDEX idx_room_id (room_id), "
        "INDEX idx_instance_id (instance_id)"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
    ))
    db.execute(text(
        "CREATE TABLE IF NOT EXISTS downstream_order_reviews ("
        "id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, "
        "source_type VARCHAR(50) NOT NULL DEFAULT 'wechat', "
        "instance_id INT UNSIGNED NULL, "
        "room_id VARCHAR(100) DEFAULT '', "
        "room_name VARCHAR(200) DEFAULT '', "
        "sender_id VARCHAR(100) DEFAULT '', "
        "sender_name VARCHAR(200) DEFAULT '', "
        "message_type VARCHAR(50) DEFAULT 'text', "
        "content_text LONGTEXT NULL, "
        "attachment_name VARCHAR(255) DEFAULT '', "
        "attachment_url VARCHAR(1000) DEFAULT '', "
        "attachment_mime VARCHAR(100) DEFAULT '', "
        "attachment_base64 LONGTEXT NULL, "
        "callback_payload LONGTEXT NULL, "
        "parse_status VARCHAR(50) NOT NULL DEFAULT 'pending', "
        "review_status VARCHAR(50) NOT NULL DEFAULT 'pending', "
        "customer_id INT UNSIGNED NULL, "
        "customer_name VARCHAR(255) DEFAULT '', "
        "ai_model VARCHAR(100) DEFAULT '', "
        "ai_error TEXT NULL, "
        "parsed_order_json LONGTEXT NULL, "
        "manual_order_json LONGTEXT NULL, "
        "erp_order_no VARCHAR(100) DEFAULT '', "
        "replaced_order_no VARCHAR(100) DEFAULT '', "
        "replace_source_ids LONGTEXT NULL, "
        "review_note TEXT NULL, "
        "reviewer_id INT UNSIGNED NULL, "
        "reviewer_name VARCHAR(100) DEFAULT '', "
        "reviewed_at DATETIME NULL, "
        "created_at DATETIME DEFAULT CURRENT_TIMESTAMP, "
        "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP, "
        "INDEX idx_room_id (room_id), "
        "INDEX idx_customer_id (customer_id), "
        "INDEX idx_parse_status (parse_status), "
        "INDEX idx_review_status (review_status), "
        "INDEX idx_created_at (created_at)"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
    ))
    db.execute(text(
        "CREATE TABLE IF NOT EXISTS internal_wechat_rooms ("
        "id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, "
        "room_id VARCHAR(100) NOT NULL, "
        "room_name VARCHAR(200) DEFAULT '', "
        "room_type VARCHAR(50) NOT NULL DEFAULT 'shipping', "
        "remark VARCHAR(500) DEFAULT '', "
        "created_at DATETIME DEFAULT CURRENT_TIMESTAMP, "
        "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP, "
        "UNIQUE KEY uk_room_id (room_id), "
        "INDEX idx_room_type (room_type)"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
    ))
    db.execute(text(
        "CREATE TABLE IF NOT EXISTS user_preferences ("
        "id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, "
        "user_id INT UNSIGNED NOT NULL, "
        "pref_key VARCHAR(100) NOT NULL, "
        "pref_value LONGTEXT NULL, "
        "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP, "
        "UNIQUE KEY uk_user_pref (user_id, pref_key)"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
    ))
    # 追加 ERP 同步相关字段（兼容已有表）
    _add_column_if_not_exists(db, "downstream_customers", "salesperson", "VARCHAR(100) DEFAULT ''")
    _add_column_if_not_exists(db, "downstream_customers", "customer_type", "VARCHAR(100) DEFAULT ''")
    _add_column_if_not_exists(db, "downstream_customers", "shipping_address", "VARCHAR(500) DEFAULT ''")
    _add_column_if_not_exists(db, "downstream_customers", "shipping_phone", "VARCHAR(100) DEFAULT ''")
    _add_column_if_not_exists(db, "downstream_customers", "short_code", "VARCHAR(100) DEFAULT ''")
    _add_column_if_not_exists(db, "downstream_customers", "telephone", "VARCHAR(100) DEFAULT ''")
    _add_column_if_not_exists(db, "downstream_customers", "nature", "VARCHAR(500) DEFAULT ''")
    _add_column_if_not_exists(db, "downstream_customers", "credit_limit", "DECIMAL(12,2) DEFAULT NULL")
    _add_column_if_not_exists(db, "downstream_customers", "synced_at", "DATETIME NULL")
    # 审核记录关联消息日志ID
    _add_column_if_not_exists(db, "downstream_order_reviews", "msg_log_id", "BIGINT UNSIGNED NULL")
    # 审核记录唯一标识（用于 ERP 备注追踪）
    _add_column_if_not_exists(db, "downstream_order_reviews", "review_uid", "VARCHAR(30) DEFAULT '' AFTER id")
    db.commit()
