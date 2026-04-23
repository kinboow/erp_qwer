<template>
  <div class="lark-dashboard">
    <!-- 顶部欢迎区域 -->
    <div class="lark-welcome-panel">
      <div class="welcome-left">
        <div class="welcome-title">
          早安，{{ userStore.realName }}，祝你度过充实的一天
        </div>
        <div class="welcome-desc">
          今天有 <strong>3</strong> 个待办任务，<strong>2</strong> 条未读消息
        </div>
      </div>
      <div class="welcome-right">
        <div class="date-widget">
          <div class="date-time">{{ currentTime }}</div>
          <div class="date-day">{{ currentDate }}</div>
        </div>
      </div>
    </div>

    <!-- 核心指标 -->
    <h3 class="section-title">核心指标</h3>
    <el-row :gutter="24" class="stat-cards-wrapper">
      <el-col :span="6" v-for="(stat, index) in statData" :key="index">
        <div class="lark-stat-card">
          <div class="stat-header">
            <span class="stat-name">{{ stat.title }}</span>
            <el-icon class="stat-icon" :style="{ color: stat.color }"><component :is="stat.icon" /></el-icon>
          </div>
          <div class="stat-body">
            <span class="stat-number">{{ stat.value }}</span>
          </div>
          <div class="stat-footer">
            <span class="trend-label">较昨日</span>
            <span class="trend-value" :class="stat.trend > 0 ? 'is-up' : 'is-down'">
              <el-icon v-if="stat.trend > 0"><Top /></el-icon>
              <el-icon v-else><Bottom /></el-icon>
              {{ Math.abs(stat.trend) }}%
            </span>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 图表和动态 -->
    <el-row :gutter="24" class="content-row">
      <el-col :span="16">
        <div class="lark-panel chart-panel">
          <div class="panel-header">
            <h3 class="panel-title">生产趋势</h3>
            <div class="panel-actions">
              <el-radio-group v-model="chartRange" size="small" class="lark-radio-group">
                <el-radio-button value="week">本周</el-radio-button>
                <el-radio-button value="month">本月</el-radio-button>
                <el-radio-button value="year">全年</el-radio-button>
              </el-radio-group>
            </div>
          </div>
          <div class="panel-body">
            <div class="lark-mock-chart">
              <div class="chart-y-axis">
                <span>10k</span><span>8k</span><span>6k</span><span>4k</span><span>2k</span><span>0</span>
              </div>
              <div class="chart-content">
                <div class="chart-bar" style="height: 30%"></div>
                <div class="chart-bar" style="height: 50%"></div>
                <div class="chart-bar" style="height: 45%"></div>
                <div class="chart-bar active" style="height: 80%"></div>
                <div class="chart-bar" style="height: 60%"></div>
                <div class="chart-bar" style="height: 40%"></div>
                <div class="chart-bar" style="height: 70%"></div>
              </div>
            </div>
            <div class="chart-x-axis">
              <span>周一</span><span>周二</span><span>周三</span><span>周四</span><span>周五</span><span>周六</span><span>周日</span>
            </div>
          </div>
        </div>
      </el-col>

      <el-col :span="8">
        <div class="lark-panel activity-panel">
          <div class="panel-header">
            <h3 class="panel-title">系统动态</h3>
            <el-button link type="primary" class="lark-link-btn">查看全部</el-button>
          </div>
          <div class="panel-body">
            <div class="lark-timeline">
              <div class="timeline-item" v-for="(item, index) in activities" :key="index">
                <div class="timeline-dot" :class="item.type"></div>
                <div class="timeline-content">
                  <div class="timeline-text">{{ item.content }}</div>
                  <div class="timeline-time">{{ item.time }}</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useUserStore } from '@/stores/user'
import {
  User, Box, Document, TrendCharts,
  Top, Bottom
} from '@element-plus/icons-vue'

const userStore = useUserStore()
const currentTime = ref('')
const currentDate = ref('')
const chartRange = ref('week')
let timer = null

const updateTime = () => {
  const now = new Date()
  currentTime.value = now.toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit' })

  const options = { month: 'long', day: 'numeric', weekday: 'long' }
  currentDate.value = now.toLocaleDateString('zh-CN', options)
}

onMounted(() => {
  updateTime()
  timer = setInterval(updateTime, 1000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})

const statData = [
  { title: '活跃用户', value: '1,284', trend: 12.5, icon: 'User', color: '#3370FF' },
  { title: '在库产品', value: '3,452', trend: 5.2, icon: 'Box', color: '#00B365' },
  { title: '待处理订单', value: '128', trend: -2.4, icon: 'Document', color: '#FF8800' },
  { title: '本月营收', value: '¥124.5k', trend: 18.2, icon: 'TrendCharts', color: '#F54A45' }
]

const activities = [
  { content: '新订单 #SO2026041501 待审批', time: '10 分钟前', type: 'primary' },
  { content: '库存盘点异常警告：A区少件', time: '1 小时前', type: 'warning' },
  { content: '发货单 #SH2026041503 已完成出库', time: '2 小时前', type: 'success' },
  { content: '系统例行数据备份完成', time: '昨天 23:00', type: 'default' },
  { content: '张三 修改了系统基础配置', time: '昨天 15:30', type: 'default' }
]
</script>

<style scoped>
.lark-dashboard {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* 欢迎面板 */
.lark-welcome-panel {
  background: var(--lark-bg-base);
  border-radius: var(--lark-radius-lg);
  padding: 24px 32px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.welcome-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--lark-text-primary);
  margin-bottom: 8px;
}

.welcome-desc {
  font-size: 14px;
  color: var(--lark-text-regular);
}

.welcome-desc strong {
  color: var(--lark-primary);
  font-weight: 600;
}

.date-widget {
  text-align: right;
}

.date-time {
  font-size: 28px;
  font-weight: 700;
  color: var(--lark-text-primary);
  line-height: 1.2;
}

.date-day {
  font-size: 14px;
  color: var(--lark-text-secondary);
}

/* 通用面板标题 */
.section-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--lark-text-primary);
  margin: 0;
  padding: 0 4px;
}

/* 统计卡片 */
.lark-stat-card {
  background: var(--lark-bg-base);
  border-radius: var(--lark-radius-lg);
  padding: 20px 24px;
  transition: transform 0.2s, box-shadow 0.2s;
  cursor: pointer;
  height: 100%;
}

.lark-stat-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--lark-shadow-hover);
}

.stat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.stat-name {
  font-size: 14px;
  color: var(--lark-text-regular);
}

.stat-icon {
  font-size: 20px;
  padding: 6px;
  background-color: var(--lark-bg-body);
  border-radius: var(--lark-radius-sm);
}

.stat-body {
  margin-bottom: 16px;
}

.stat-number {
  font-size: 32px;
  font-weight: 700;
  color: var(--lark-text-primary);
  line-height: 1.2;
}

.stat-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.trend-label {
  color: var(--lark-text-secondary);
}

.trend-value {
  display: flex;
  align-items: center;
  font-weight: 500;
}

.trend-value.is-up {
  color: #F54A45;
}

.trend-value.is-down {
  color: #00B365;
}

/* 通用面板 */
.lark-panel {
  background: var(--lark-bg-base);
  border-radius: var(--lark-radius-lg);
  display: flex;
  flex-direction: column;
  height: 100%;
}

.panel-header {
  padding: 20px 24px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid transparent; /* 可选的分割线 */
}

.panel-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--lark-text-primary);
  margin: 0;
}

.panel-body {
  padding: 0 24px 24px;
  flex: 1;
}

.chart-panel {
  min-height: 380px;
}

.activity-panel {
  min-height: 380px;
}

/* 飞书风格单选按钮 */
:deep(.lark-radio-group .el-radio-button__inner) {
  border: none !important;
  background-color: var(--lark-bg-hover);
  color: var(--lark-text-regular);
  box-shadow: none !important;
  border-radius: var(--lark-radius-sm) !important;
  margin-left: 4px;
  padding: 6px 16px;
}

:deep(.lark-radio-group .el-radio-button.is-active .el-radio-button__inner) {
  background-color: var(--lark-bg-base);
  color: var(--lark-primary);
  box-shadow: 0 2px 6px rgba(0,0,0,0.06) !important;
  font-weight: 500;
}

.lark-link-btn {
  font-weight: 500;
  font-size: 14px;
}

/* 飞书极简风格占位图表 */
.lark-mock-chart {
  display: flex;
  height: 250px;
  margin-top: 20px;
}

.chart-y-axis {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding-right: 16px;
  color: var(--lark-text-secondary);
  font-size: 12px;
  text-align: right;
  width: 40px;
  border-right: 1px dashed var(--lark-border-light);
}

.chart-content {
  flex: 1;
  display: flex;
  align-items: flex-end;
  justify-content: space-around;
  padding: 0 10px;
}

.chart-bar {
  width: 32px;
  background-color: var(--lark-primary-light);
  border-radius: 4px 4px 0 0;
  transition: all 0.3s ease;
  position: relative;
}

.chart-bar:hover, .chart-bar.active {
  background-color: var(--lark-primary);
}

.chart-x-axis {
  display: flex;
  justify-content: space-around;
  margin-left: 40px;
  padding-top: 12px;
  color: var(--lark-text-secondary);
  font-size: 12px;
}

/* 飞书极简时间轴 */
.lark-timeline {
  display: flex;
  flex-direction: column;
  gap: 20px;
  margin-top: 10px;
}

.timeline-item {
  display: flex;
  gap: 12px;
  position: relative;
}

.timeline-item:not(:last-child)::before {
  content: '';
  position: absolute;
  left: 3px;
  top: 14px;
  bottom: -20px;
  width: 2px;
  background-color: var(--lark-border-light);
}

.timeline-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: var(--lark-border);
  margin-top: 6px;
  position: relative;
  z-index: 1;
}

.timeline-dot.primary { background-color: var(--lark-primary); box-shadow: 0 0 0 3px var(--lark-primary-light); }
.timeline-dot.success { background-color: #00B365; }
.timeline-dot.warning { background-color: #FF8800; }

.timeline-content {
  flex: 1;
}

.timeline-text {
  font-size: 14px;
  color: var(--lark-text-primary);
  margin-bottom: 4px;
  line-height: 1.5;
}

.timeline-time {
  font-size: 12px;
  color: var(--lark-text-secondary);
}
</style>
