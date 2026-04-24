<template>
  <div class="lark-dashboard">
    <!-- 顶部欢迎区域 -->
    <div class="lark-welcome-panel">
      <div class="welcome-left">
        <div class="welcome-title">
          {{ greeting }}，{{ userStore.realName }}，{{ greetingSuffix }}
        </div>
        <div class="welcome-desc">
          <template v-if="stats.pending_orders > 0">
            当前有 <strong>{{ stats.pending_orders }}</strong> 个待审核订单
          </template>
          <template v-else>暂无待处理事项</template>
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
    <el-row :gutter="24" class="stat-cards-wrapper">
      <el-col :span="6" v-for="(stat, index) in statCards" :key="index">
        <div class="lark-stat-card">
          <div class="stat-header">
            <span class="stat-name">{{ stat.title }}</span>
            <span class="stat-icon-wrap" :style="{ background: stat.color }">
              <img class="stat-icon" :src="stat.icon" />
            </span>
          </div>
          <div class="stat-body">
            <span class="stat-number">{{ stat.value }}</span>
          </div>
          <div class="stat-footer" v-if="stat.trendLabel || stat.trend !== null">
            <span class="trend-label">{{ stat.trendLabel }}</span>
            <span v-if="stat.trend !== null" class="trend-value" :class="stat.trend > 0 ? 'is-up' : stat.trend < 0 ? 'is-down' : ''">
              <el-icon v-if="stat.trend > 0"><Top /></el-icon>
              <el-icon v-else-if="stat.trend < 0"><Bottom /></el-icon>
              {{ stat.trend === 0 ? '持平' : Math.abs(stat.trend).toFixed(1) + '%' }}
            </span>
          </div>
        </div>
      </el-col>
      <!-- 第四列：两个小状态卡片 -->
      <el-col :span="6">
        <div class="status-card-group">
          <div class="mini-status-card" :class="stats.wechat_online ? 'online' : 'offline'">
            <div class="mini-status-dot" :class="stats.wechat_online ? 'green' : 'red'"></div>
            <div class="mini-status-info">
              <div class="mini-status-label">企业微信</div>
              <div class="mini-status-text">{{ stats.wechat_online ? '已连接' : '未连接' }}</div>
            </div>
            <img class="mini-status-icon" :src="iconWechatStatus" alt="企业微信状态" />
          </div>
          <div class="mini-status-card" :class="stats.erp_online ? 'online' : 'offline'">
            <div class="mini-status-dot" :class="stats.erp_online ? 'green' : 'red'"></div>
            <div class="mini-status-info">
              <div class="mini-status-label">ERP 服务</div>
              <div class="mini-status-text">{{ stats.erp_online ? '运行中' : '未启动' }}</div>
            </div>
            <img class="mini-status-icon" :src="iconErpStatus" alt="ERP 服务状态" />
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 图表和动态 -->
    <el-row :gutter="24" class="content-row">
      <el-col :span="16">
        <div class="lark-panel chart-panel">
          <div class="panel-header">
            <h3 class="panel-title">订单与发货趋势</h3>
            <div class="range-switcher">
              <span
                v-for="r in rangeOptions" :key="r.value"
                class="range-btn" :class="{ active: chartRange === r.value }"
                @click="switchRange(r.value)"
              >{{ r.label }}</span>
            </div>
          </div>
          <div class="panel-body">
            <div class="chart-legend">
              <span class="legend-item"><span class="legend-dot order"></span>订单</span>
              <span class="legend-item"><span class="legend-dot shipment"></span>发货单</span>
            </div>
            <div class="line-chart-wrapper" ref="chartWrapperRef">
              <svg :key="chartAnimKey" :viewBox="`0 0 ${svgW} ${svgH}`" class="line-chart-svg" preserveAspectRatio="none"
                @mousemove="onChartMouseMove" @mouseleave="onChartMouseLeave">
                <!-- 网格线 -->
                <line v-for="(y, i) in gridLines" :key="'g'+i" :x1="padL" :y1="y" :x2="svgW - padR" :y2="y" class="grid-line" />
                <!-- 订单折线 -->
                <polyline :points="orderPoints" class="chart-line order-line animated-line" fill="none" :style="{ strokeDasharray: orderLineLen, strokeDashoffset: orderLineLen }" />
                <!-- 发货折线 -->
                <polyline :points="shipmentPoints" class="chart-line shipment-line animated-line" fill="none" :style="{ strokeDasharray: shipmentLineLen, strokeDashoffset: shipmentLineLen, animationDelay: '0.15s' }" />
                <!-- 数据点 -->
                <circle v-for="(p, i) in orderDots" :key="'o'+i" :cx="p.x" :cy="p.y" r="3" class="chart-dot order-dot" />
                <circle v-for="(p, i) in shipmentDots" :key="'s'+i" :cx="p.x" :cy="p.y" r="3" class="chart-dot shipment-dot" />
                <!-- hover 辅助线 -->
                <template v-if="hoverIdx >= 0">
                  <line :x1="orderDots[hoverIdx]?.x" :y1="padT" :x2="orderDots[hoverIdx]?.x" :y2="svgH - padB" class="hover-guide-line" />
                  <circle :cx="orderDots[hoverIdx]?.x" :cy="orderDots[hoverIdx]?.y" r="4" class="hover-dot order-dot" />
                  <circle :cx="shipmentDots[hoverIdx]?.x" :cy="shipmentDots[hoverIdx]?.y" r="4" class="hover-dot shipment-dot" />
                </template>
              </svg>
              <!-- Tooltip -->
              <div v-if="hoverIdx >= 0" class="chart-tooltip" :style="tooltipStyle">
                <div class="tooltip-date">{{ tooltipData.date }}</div>
                <div class="tooltip-row">
                  <span class="tooltip-dot order"></span>
                  <span class="tooltip-label">订单</span>
                  <span class="tooltip-val">{{ tooltipData.orders }}</span>
                </div>
                <div class="tooltip-row">
                  <span class="tooltip-dot shipment"></span>
                  <span class="tooltip-label">发货单</span>
                  <span class="tooltip-val">{{ tooltipData.shipments }}</span>
                </div>
              </div>
              <!-- Y轴标签 -->
              <div class="y-labels">
                <span v-for="(v, i) in yAxisLabels" :key="i" :style="{ top: gridLinePercents[i] }">{{ v }}</span>
              </div>
            </div>
            <div class="x-labels">
              <span v-for="(d, i) in xLabels" :key="i">{{ d }}</span>
            </div>
          </div>
        </div>
      </el-col>

      <el-col :span="8">
        <div class="lark-panel activity-panel">
          <div class="panel-header">
            <h3 class="panel-title">数据概览</h3>
          </div>
          <div class="panel-body">
            <div class="overview-list">
              <div class="overview-item" v-for="item in overviewItems" :key="item.label">
                <span class="overview-label">{{ item.label }}</span>
                <span class="overview-value">{{ item.value }}</span>
              </div>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 系统动态 -->
    <el-row :gutter="24" class="content-row">
      <el-col :span="24">
        <div class="lark-panel">
          <div class="panel-header">
            <h3 class="panel-title">系统动态</h3>
          </div>
          <div class="panel-body">
            <div v-if="activities.length === 0" class="empty-activity">暂无动态</div>
            <div v-else class="lark-timeline">
              <div class="timeline-item" v-for="(item, index) in activities" :key="index">
                <div class="timeline-dot" :class="item.type"></div>
                <div class="timeline-content">
                  <div class="timeline-text">{{ item.content }}</div>
                  <div class="timeline-time">{{ item.time }}</div>
                </div>
              </div>
            </div>
          </div>
</template>

<script setup>
  import { ref, computed, onMounted, onUnmounted } from 'vue'
  import { useUserStore } from '@/stores/user'
  import { Top, Bottom } from '@element-plus/icons-vue'
  import iconProduct from '@/assets/icons/product.svg'
  import iconOrder from '@/assets/icons/order.svg'
  import iconShipment from '@/assets/icons/shipment.svg'
  import iconWechatStatus from '@/assets/icons/企业微信.svg'
  import iconErpStatus from '@/assets/icons/数据连接_(1).svg'
  import request from '@/utils/request'

  const userStore = useUserStore()
  const currentTime = ref('')
  const currentDate = ref('')
  const greeting = ref('')
  const greetingSuffix = ref('')
  let timer = null

  const stats = ref({
    user_count: 0,
    product_count: 0,
    total_orders: 0,
    pending_orders: 0,
    today_orders: 0,
    yesterday_orders: 0,
    total_shipments: 0,
    today_shipments: 0,
    yesterday_shipments: 0,
    month_revenue: 0,
    last_month_revenue: 0,
    pending_downstream: 0,
    daily_orders: [],
    daily_shipments: [],
    recent_activities: [],
    wechat_online: false,
    erp_online: false,
  })

  // ...

  .mini-status-dot.red {
    background-color: #F54A45;
    box-shadow: 0 0 0 3px rgba(245,74,69,0.15);
  }

  .mini-status-info {
    display: flex;
    flex-direction: column;
    gap: 2px;
    flex: 1;
  }

  .mini-status-label {
    font-size: 12px;
    color: var(--lark-text-secondary);
    line-height: 1;
  }

  .mini-status-card.online .mini-status-text {
    color: #00B365;
  }

  .mini-status-card.offline .mini-status-text {
    color: var(--lark-text-secondary);
  }

  .mini-status-icon {
    width: 24px;
    height: 24px;
    flex-shrink: 0;
    object-fit: contain;
  }

  /* ... */
</script>

<style scoped>
  /* ... */
</style>
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

/* 时间范围切换器 */
.range-switcher {
  display: flex;
  gap: 4px;
  background: var(--lark-bg-body, #f5f6f7);
  border-radius: 6px;
  padding: 3px;
}

.range-btn {
  font-size: 12px;
  padding: 4px 14px;
  border-radius: 4px;
  cursor: pointer;
  color: var(--lark-text-secondary);
  transition: all 0.2s;
  user-select: none;
  font-weight: 500;
}

.range-btn:hover {
  color: var(--lark-text-primary);
}

.range-btn.active {
  background: var(--lark-bg-base, #fff);
  color: var(--lark-primary, #3370ff);
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}

/* 图表图例 */
.chart-legend {
  display: flex;
  gap: 20px;
  margin-bottom: 8px;
  font-size: 13px;
  color: var(--lark-text-regular);
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.legend-dot.order {
  background-color: var(--lark-primary, #3370FF);
}

.legend-dot.shipment {
  background-color: #00B365;
}

/* SVG 折线图 */
.line-chart-wrapper {
  position: relative;
  height: 260px;
  margin-top: 8px;
  margin-left: 48px;
}

.line-chart-svg {
  width: 100%;
  height: 100%;
}

.grid-line {
  stroke: var(--lark-border-light, #eee);
  stroke-width: 1;
  stroke-dasharray: 4 3;
}

.chart-line {
  stroke-width: 2.5;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.animated-line {
  animation: line-draw 0.8s ease forwards;
}

@keyframes line-draw {
  to { stroke-dashoffset: 0; }
}

.order-line {
  stroke: var(--lark-primary, #3370FF);
}

.shipment-line {
  stroke: #00B365;
}

.chart-dot {
  stroke: #fff;
  stroke-width: 1.5;
}

.chart-dot.order-dot {
  fill: var(--lark-primary, #3370FF);
}

.chart-dot.shipment-dot {
  fill: #00B365;
}

.hover-guide-line {
  stroke: var(--lark-text-secondary, #999);
  stroke-width: 1;
  stroke-dasharray: 3 2;
  pointer-events: none;
}

.hover-dot {
  pointer-events: none;
  stroke: #fff;
  stroke-width: 2;
}

.hover-dot.order-dot {
  fill: var(--lark-primary, #3370FF);
}

.hover-dot.shipment-dot {
  fill: #00B365;
}

.chart-tooltip {
  position: absolute;
  z-index: 10;
  background: var(--lark-bg-base, #fff);
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.12);
  padding: 12px 16px;
  min-width: 140px;
  pointer-events: none;
  font-size: 13px;
  line-height: 1.6;
}

.tooltip-date {
  font-weight: 600;
  color: var(--lark-text-primary);
  margin-bottom: 6px;
  white-space: nowrap;
}

.tooltip-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.tooltip-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.tooltip-dot.order {
  background: var(--lark-primary, #3370FF);
}

.tooltip-dot.shipment {
  background: #00B365;
}

.tooltip-label {
  color: var(--lark-text-secondary);
  flex: 1;
}

.tooltip-val {
  font-weight: 600;
  color: var(--lark-text-primary);
}

.y-labels {
  position: absolute;
  left: -44px;
  top: 0;
  bottom: 0;
  width: 40px;
  pointer-events: none;
}

.y-labels span {
  position: absolute;
  right: 0;
  font-size: 11px;
  color: var(--lark-text-secondary);
  transform: translateY(-50%);
  text-align: right;
}

.x-labels {
  display: flex;
  justify-content: space-between;
  padding-top: 10px;
  margin-left: 48px;
  padding-left: 1.25%;
  padding-right: 1.25%;
  color: var(--lark-text-secondary);
  font-size: 11px;
}

/* 数据概览列表 */
.overview-list {
  display: flex;
  flex-direction: column;
  gap: 0;
  margin-top: 4px;
}

.overview-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 0;
  border-bottom: 1px solid var(--lark-border-light, #f0f0f0);
}

.overview-item:last-child {
  border-bottom: none;
}

.overview-label {
  font-size: 14px;
  color: var(--lark-text-regular);
}

.overview-value {
  font-size: 16px;
  font-weight: 600;
  color: var(--lark-text-primary);
}

/* 系统动态时间轴 */
.empty-activity {
  text-align: center;
  color: var(--lark-text-secondary);
  padding: 32px 0;
  font-size: 14px;
}

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
  flex-shrink: 0;
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
