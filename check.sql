-- 1. テーブル一覧と作成コマンドの確認 (構造のすべてがわかります)
SHOW CREATE TABLE device_catalog;
SHOW CREATE TABLE nodes;
SHOW CREATE TABLE node_commands;
SHOW CREATE TABLE node_configs;
SHOW CREATE TABLE node_data;
SHOW CREATE TABLE node_status_current;
SHOW CREATE TABLE system_logs;
SHOW CREATE TABLE vst_links;

-- 2. カラム詳細、デフォルト値、インデックスの確認
SHOW FULL COLUMNS FROM device_catalog;
SHOW FULL COLUMNS FROM nodes;
SHOW FULL COLUMNS FROM node_commands;
SHOW FULL COLUMNS FROM node_configs;
SHOW FULL COLUMNS FROM node_data;
SHOW FULL COLUMNS FROM node_status_current;
SHOW FULL COLUMNS FROM system_logs;
SHOW FULL COLUMNS FROM vst_links;

-- 3. インデックス（ユニーク制約）の確認
SHOW INDEX FROM device_catalog;
SHOW INDEX FROM nodes;
SHOW INDEX FROM node_commands;
SHOW INDEX FROM node_configs;
SHOW INDEX FROM node_data;
SHOW INDEX FROM node_status_current;
SHOW INDEX FROM system_logs;
SHOW INDEX FROM vst_links;