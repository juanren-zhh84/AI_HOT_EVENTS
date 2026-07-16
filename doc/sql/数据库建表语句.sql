-- GitHub 热点项目自动化监控服务 MySQL 建表语句
-- 建议版本：MySQL 8.0.16+
-- 说明：
-- 1. 使用 utf8mb4 字符集，支持中文、Emoji、GitHub Topic 等内容。
-- 2. 使用 JSON 字段保存 topics、tags、filters、tech_stack、preferences 等结构化扩展数据。
-- 3. id 默认使用 UUID() 生成；如果你的 MySQL 版本不支持表达式默认值，可改为由 Python 应用生成 UUID。

SET NAMES utf8mb4;
SET time_zone = '+00:00';

CREATE TABLE IF NOT EXISTS repositories (
    id CHAR(36) NOT NULL DEFAULT (UUID()) COMMENT '主键',
    owner VARCHAR(255) NOT NULL COMMENT 'GitHub 仓库 owner',
    name VARCHAR(255) NOT NULL COMMENT '仓库名',
    full_name VARCHAR(511) NOT NULL COMMENT '仓库全名，格式 owner/repo',
    html_url TEXT NOT NULL COMMENT 'GitHub 页面地址',
    homepage TEXT NULL COMMENT '项目主页',
    description TEXT NULL COMMENT '仓库描述',
    primary_language VARCHAR(100) NULL COMMENT '主语言',
    topics JSON NOT NULL DEFAULT (JSON_ARRAY()) COMMENT 'GitHub topics',
    license_name VARCHAR(255) NULL COMMENT '许可证名称',
    stars INT NOT NULL DEFAULT 0 COMMENT '当前星标数',
    forks INT NOT NULL DEFAULT 0 COMMENT '当前 fork 数',
    watchers INT NOT NULL DEFAULT 0 COMMENT '当前 watchers 数',
    open_issues INT NOT NULL DEFAULT 0 COMMENT '当前 open issue 数',
    archived TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否归档',
    disabled TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否不可用',
    enabled TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用监控',
    source VARCHAR(100) NOT NULL DEFAULT 'manual' COMMENT '来源',
    tags JSON NOT NULL DEFAULT (JSON_ARRAY()) COMMENT '本地标签',
    github_created_at DATETIME(3) NULL COMMENT 'GitHub 创建时间',
    github_updated_at DATETIME(3) NULL COMMENT 'GitHub 更新时间',
    last_pushed_at DATETIME(3) NULL COMMENT '最近 push 时间',
    last_collected_at DATETIME(3) NULL COMMENT '最近采集时间',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uq_repositories_full_name (full_name),
    KEY idx_repositories_enabled (enabled),
    KEY idx_repositories_language (primary_language),
    KEY idx_repositories_stars (stars),
    KEY idx_repositories_last_collected_at (last_collected_at),
    FULLTEXT KEY ft_repositories_search (full_name, description)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='GitHub 仓库表';

CREATE TABLE IF NOT EXISTS monitor_sources (
    id CHAR(36) NOT NULL DEFAULT (UUID()) COMMENT '主键',
    name VARCHAR(255) NOT NULL COMMENT '监控源名称',
    type ENUM('manual', 'github_search', 'topic', 'owner') NOT NULL COMMENT '监控源类型',
    query TEXT NOT NULL COMMENT '监控源查询表达式',
    filters JSON NOT NULL DEFAULT (JSON_OBJECT()) COMMENT '过滤条件',
    enabled TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
    discover_interval_minutes INT NOT NULL DEFAULT 360 COMMENT '发现任务间隔，单位分钟',
    last_discovered_at DATETIME(3) NULL COMMENT '最近发现时间',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
    PRIMARY KEY (id),
    KEY idx_monitor_sources_enabled (enabled),
    KEY idx_monitor_sources_type (type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='监控源表';

CREATE TABLE IF NOT EXISTS star_snapshots (
    id CHAR(36) NOT NULL DEFAULT (UUID()) COMMENT '主键',
    repository_id CHAR(36) NOT NULL COMMENT '仓库 ID',
    stars INT NOT NULL COMMENT '快照星标数',
    forks INT NOT NULL DEFAULT 0 COMMENT '快照 fork 数',
    watchers INT NOT NULL DEFAULT 0 COMMENT '快照 watchers 数',
    open_issues INT NOT NULL DEFAULT 0 COMMENT '快照 open issue 数',
    source VARCHAR(100) NOT NULL DEFAULT 'github_rest' COMMENT '采集来源',
    snapshot_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '快照时间',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
    PRIMARY KEY (id),
    UNIQUE KEY uq_star_snapshots_repo_time (repository_id, snapshot_at),
    KEY idx_star_snapshots_repo_time (repository_id, snapshot_at),
    KEY idx_star_snapshots_snapshot_at (snapshot_at),
    CONSTRAINT fk_star_snapshots_repository
        FOREIGN KEY (repository_id) REFERENCES repositories (id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='星标快照表';

CREATE TABLE IF NOT EXISTS project_profiles (
    id CHAR(36) NOT NULL DEFAULT (UUID()) COMMENT '主键',
    repository_id CHAR(36) NOT NULL COMMENT '仓库 ID',
    summary TEXT NULL COMMENT '一句话简介',
    features JSON NOT NULL DEFAULT (JSON_ARRAY()) COMMENT '功能点',
    audience JSON NOT NULL DEFAULT (JSON_ARRAY()) COMMENT '适用人群',
    highlights JSON NOT NULL DEFAULT (JSON_ARRAY()) COMMENT '项目亮点',
    tech_stack JSON NOT NULL DEFAULT (JSON_OBJECT()) COMMENT '技术栈',
    readme_hash VARCHAR(128) NULL COMMENT 'README 内容哈希',
    summary_status ENUM('complete', 'partial', 'failed') NOT NULL DEFAULT 'partial' COMMENT '摘要状态',
    generated_at DATETIME(3) NULL COMMENT '生成时间',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uq_project_profiles_repository (repository_id),
    KEY idx_project_profiles_summary_status (summary_status),
    CONSTRAINT fk_project_profiles_repository
        FOREIGN KEY (repository_id) REFERENCES repositories (id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='项目画像表';

CREATE TABLE IF NOT EXISTS hot_projects (
    id CHAR(36) NOT NULL DEFAULT (UUID()) COMMENT '主键',
    repository_id CHAR(36) NOT NULL COMMENT '仓库 ID',
    report_date DATE NOT NULL COMMENT '统计日期',
    rank_no INT NOT NULL COMMENT '排名',
    hot_score DECIMAL(12, 4) NOT NULL DEFAULT 0 COMMENT '热度分',
    stars INT NOT NULL DEFAULT 0 COMMENT '统计时总星标',
    stars_delta_24h INT NOT NULL DEFAULT 0 COMMENT '24 小时新增星标',
    stars_delta_7d INT NOT NULL DEFAULT 0 COMMENT '7 日新增星标',
    growth_rate_24h DECIMAL(12, 6) NOT NULL DEFAULT 0 COMMENT '24 小时增长率',
    reason TEXT NULL COMMENT '入选原因',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uq_hot_projects_report_repo (report_date, repository_id),
    UNIQUE KEY uq_hot_projects_report_rank (report_date, rank_no),
    KEY idx_hot_projects_report_date_rank (report_date, rank_no),
    KEY idx_hot_projects_hot_score (hot_score),
    CONSTRAINT fk_hot_projects_repository
        FOREIGN KEY (repository_id) REFERENCES repositories (id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='每日热点项目表';

CREATE TABLE IF NOT EXISTS subscribers (
    id CHAR(36) NOT NULL DEFAULT (UUID()) COMMENT '主键',
    email VARCHAR(320) NOT NULL COMMENT '订阅者邮箱',
    name VARCHAR(255) NULL COMMENT '订阅者名称',
    status ENUM('active', 'paused', 'unsubscribed') NOT NULL DEFAULT 'active' COMMENT '订阅状态',
    preferences JSON NOT NULL DEFAULT (JSON_OBJECT()) COMMENT '订阅偏好',
    unsubscribe_token CHAR(36) NOT NULL DEFAULT (UUID()) COMMENT '退订 token',
    unsubscribed_at DATETIME(3) NULL COMMENT '退订时间',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uq_subscribers_email (email),
    UNIQUE KEY uq_subscribers_unsubscribe_token (unsubscribe_token),
    KEY idx_subscribers_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='邮件订阅者表';

CREATE TABLE IF NOT EXISTS email_reports (
    id CHAR(36) NOT NULL DEFAULT (UUID()) COMMENT '主键',
    report_date DATE NOT NULL COMMENT '日报日期',
    subject VARCHAR(255) NOT NULL COMMENT '邮件标题',
    html_content MEDIUMTEXT NOT NULL COMMENT 'HTML 邮件内容',
    text_content MEDIUMTEXT NOT NULL COMMENT '纯文本邮件内容',
    status ENUM('draft', 'sending', 'sent', 'failed') NOT NULL DEFAULT 'draft' COMMENT '报告状态',
    generated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '生成时间',
    sent_at DATETIME(3) NULL COMMENT '发送时间',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uq_email_reports_report_date (report_date),
    KEY idx_email_reports_report_date (report_date),
    KEY idx_email_reports_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='邮件日报表';

CREATE TABLE IF NOT EXISTS email_deliveries (
    id CHAR(36) NOT NULL DEFAULT (UUID()) COMMENT '主键',
    report_id CHAR(36) NOT NULL COMMENT '日报 ID',
    subscriber_id CHAR(36) NOT NULL COMMENT '订阅者 ID',
    email VARCHAR(320) NOT NULL COMMENT '实际发送邮箱',
    status ENUM('pending', 'sending', 'sent', 'failed', 'skipped') NOT NULL DEFAULT 'pending' COMMENT '发送状态',
    retry_count INT NOT NULL DEFAULT 0 COMMENT '重试次数',
    error_message TEXT NULL COMMENT '失败原因',
    sent_at DATETIME(3) NULL COMMENT '发送时间',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uq_email_deliveries_report_subscriber (report_id, subscriber_id),
    KEY idx_email_deliveries_report_id (report_id),
    KEY idx_email_deliveries_subscriber_id (subscriber_id),
    KEY idx_email_deliveries_status (status),
    CONSTRAINT fk_email_deliveries_report
        FOREIGN KEY (report_id) REFERENCES email_reports (id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_email_deliveries_subscriber
        FOREIGN KEY (subscriber_id) REFERENCES subscribers (id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='邮件投递记录表';

CREATE TABLE IF NOT EXISTS jobs (
    id CHAR(36) NOT NULL DEFAULT (UUID()) COMMENT '主键',
    type VARCHAR(50) NOT NULL COMMENT '任务类型',
    status ENUM('pending', 'running', 'succeeded', 'failed', 'cancelled') NOT NULL DEFAULT 'pending' COMMENT '任务状态',
    payload JSON NOT NULL DEFAULT (JSON_OBJECT()) COMMENT '任务参数',
    progress JSON NOT NULL DEFAULT (JSON_OBJECT()) COMMENT '任务进度',
    error_message TEXT NULL COMMENT '错误信息',
    started_at DATETIME(3) NULL COMMENT '开始时间',
    finished_at DATETIME(3) NULL COMMENT '结束时间',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
    PRIMARY KEY (id),
    KEY idx_jobs_type_status (type, status),
    KEY idx_jobs_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='异步任务表';

CREATE TABLE IF NOT EXISTS schedules (
    id VARCHAR(100) NOT NULL COMMENT '调度 ID',
    name VARCHAR(100) NOT NULL COMMENT '调度名称',
    cron_expr VARCHAR(100) NOT NULL COMMENT 'Cron 表达式',
    timezone VARCHAR(100) NOT NULL DEFAULT 'Asia/Shanghai' COMMENT '时区',
    enabled TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
    next_run_at DATETIME(3) NULL COMMENT '下次运行时间',
    last_run_at DATETIME(3) NULL COMMENT '最近运行时间',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uq_schedules_name (name),
    KEY idx_schedules_enabled (enabled),
    KEY idx_schedules_next_run_at (next_run_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='调度配置表';

INSERT INTO schedules (id, name, cron_expr, timezone, enabled)
VALUES
    ('schedule_discovery', 'repository_discovery', '0 */6 * * *', 'Asia/Shanghai', 1),
    ('schedule_star_snapshot', 'star_snapshot', '0 * * * *', 'Asia/Shanghai', 1),
    ('schedule_profile_refresh', 'profile_refresh', '0 2 * * *', 'Asia/Shanghai', 1),
    ('schedule_hot_project_calculate', 'hot_project_calculate', '30 8 * * *', 'Asia/Shanghai', 1),
    ('schedule_daily_digest', 'daily_digest', '0 9 * * *', 'Asia/Shanghai', 1)
ON DUPLICATE KEY UPDATE id = id;

