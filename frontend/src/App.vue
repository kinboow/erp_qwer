<template>
  <el-config-provider :button="{ autoInsertSpace: true }">
    <router-view />
  </el-config-provider>
</template>

<script setup>
import { ElConfigProvider } from 'element-plus'
</script>

<style>
/* 飞书设计规范 CSS 变量 */
:root {
  --lark-primary: #3370FF;
  --lark-primary-hover: #5487FF;
  --lark-primary-active: #2458db;
  --lark-primary-light: #eef2ff;

  --lark-bg-body: #f5f6f7;
  --lark-bg-base: #ffffff;
  --lark-bg-layout: #ffffff;
  --lark-bg-sidebar: #f8f9fa;
  --lark-bg-hover: #f0f1f4;
  --lark-bg-active: #e6e8eb;

  --lark-text-primary: #1f2329;
  --lark-text-regular: #646a73;
  --lark-text-secondary: #8f959e;
  --lark-text-disabled: #bbbfc4;

  --lark-border: #dee0e3;
  --lark-border-light: #e4e6e9;

  --lark-radius: 8px;
  --lark-radius-lg: 12px;
  --lark-radius-sm: 4px;

  --lark-shadow: 0 4px 10px rgba(31, 35, 41, 0.05);
  --lark-shadow-hover: 0 8px 24px rgba(31, 35, 41, 0.08);
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html, body, #app {
  height: 100%;
  /* 飞书常用中文字体栈 */
  font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Helvetica Neue", Helvetica, Arial, sans-serif;
  color: var(--lark-text-primary);
  background-color: var(--lark-bg-body);
  -webkit-font-smoothing: antialiased;
}

/* 全局覆盖 Element Plus 的一些基础样式，使其更像飞书 */
.el-button--primary {
  --el-button-bg-color: var(--lark-primary);
  --el-button-border-color: var(--lark-primary);
  --el-button-hover-bg-color: var(--lark-primary-hover);
  --el-button-hover-border-color: var(--lark-primary-hover);
  --el-button-active-bg-color: var(--lark-primary-active);
}

.el-button {
  --el-border-radius-base: var(--lark-radius-sm);
  font-weight: 500;
}

.el-card {
  --el-card-border-color: transparent;
  --el-card-border-radius: var(--lark-radius);
  box-shadow: 0 1px 2px -2px rgba(0, 0, 0, 0.08), 0 3px 6px 0 rgba(0, 0, 0, 0.06), 0 5px 12px 4px rgba(0, 0, 0, 0.04) !important;
}

.el-input__wrapper, .el-select__wrapper {
  --el-input-border-radius: var(--lark-radius-sm);
  box-shadow: 0 0 0 1px var(--lark-border) inset !important;
}

.el-input__wrapper.is-focus, .el-select__wrapper.is-focus {
  box-shadow: 0 0 0 1px var(--lark-primary) inset, 0 0 0 2px var(--lark-primary-light) inset !important;
}

/* 覆盖表格样式 */
.el-table {
  --el-table-border-color: var(--lark-border-light);
  --el-table-header-text-color: var(--lark-text-regular);
  --el-table-text-color: var(--lark-text-primary);
  font-size: 14px;
}

.el-table th.el-table__cell {
  background-color: var(--lark-bg-sidebar) !important;
  font-weight: 600;
}

/* 对话框圆角 */
.el-dialog {
  --el-dialog-border-radius: var(--lark-radius-lg);
  box-shadow: var(--lark-shadow-hover);
}
</style>
