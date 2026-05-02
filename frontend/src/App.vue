<template>
  <el-config-provider :button="{ autoInsertSpace: true }">
    <router-view />
  </el-config-provider>
</template>

<script setup>
import { onMounted, onUnmounted } from 'vue'
import { ElConfigProvider } from 'element-plus'

/* 全局：监听 tooltip 弹出后修正位置，确保不超出视口 */
let _tooltipObserver = null
const _clamping = new WeakSet()
onMounted(() => {
  const pad = 8
  function clampTooltip(el) {
    if (!el || !el.classList.contains('is-dark') || _clamping.has(el)) return
    _clamping.add(el)
    requestAnimationFrame(() => {
      const rect = el.getBoundingClientRect()
      const vw = window.innerWidth
      const vh = window.innerHeight
      let dx = 0, dy = 0
      if (rect.right > vw - pad) dx = vw - pad - rect.right
      if (rect.left < pad) dx = pad - rect.left
      if (rect.bottom > vh - pad) dy = vh - pad - rect.bottom
      if (rect.top < pad) dy = pad - rect.top
      if (dx || dy) {
        const cur = window.getComputedStyle(el).transform
        const m = cur && cur !== 'none' ? cur : 'matrix(1,0,0,1,0,0)'
        const match = m.match(/matrix.*\((.+)\)/)
        if (match) {
          const vals = match[1].split(',').map(Number)
          vals[4] = (vals[4] || 0) + dx
          vals[5] = (vals[5] || 0) + dy
          el.style.transform = `matrix(${vals.join(',')})`
        }
      }
      setTimeout(() => _clamping.delete(el), 50)
    })
  }
  _tooltipObserver = new MutationObserver((mutations) => {
    for (const m of mutations) {
      for (const node of m.addedNodes) {
        if (node.nodeType === 1 && node.classList && node.classList.contains('el-popper')) {
          clampTooltip(node)
        }
      }
      if (m.type === 'attributes' && m.target.classList && m.target.classList.contains('el-popper') && m.target.classList.contains('is-dark')) {
        clampTooltip(m.target)
      }
    }
  })
  _tooltipObserver.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['data-popper-placement'] })
})
onUnmounted(() => {
  if (_tooltipObserver) _tooltipObserver.disconnect()
})
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

/* 全局表格单元格：超出省略 */
.el-table .el-table__cell .cell {
  overflow: hidden !important;
  text-overflow: ellipsis !important;
  white-space: nowrap !important;
}

/* 表格溢出提示框：自适应视口、换行、超长可滚动 */
.el-popper.is-dark {
  max-width: min(480px, calc(100vw - 24px)) !important;
  max-height: min(320px, calc(100vh - 40px)) !important;
  overflow-y: auto !important;
  overflow-x: hidden !important;
  white-space: pre-wrap !important;
  word-break: break-word !important;
  line-height: 1.6 !important;
  scrollbar-width: thin !important;
  scrollbar-color: rgba(255,255,255,0.35) transparent !important;
}
.el-popper.is-dark::-webkit-scrollbar {
  width: 5px !important;
}
.el-popper.is-dark::-webkit-scrollbar-thumb {
  background: rgba(255,255,255,0.35) !important;
  border-radius: 3px !important;
}
.el-popper.is-dark::-webkit-scrollbar-track {
  background: transparent !important;
}

/* 全局隐藏滚动条，保留滚动功能 */
*,
*::before,
*::after {
  scrollbar-width: none !important;
  -ms-overflow-style: none !important;
}
*::-webkit-scrollbar {
  display: none !important;
}
</style>
