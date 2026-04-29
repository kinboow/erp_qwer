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
          <el-tooltip :content="stats.wechat_error || '企业微信服务正常'" placement="left" :disabled="stats.wechat_online">
            <div class="mini-status-card" :class="stats.wechat_online ? 'online' : 'offline'" @click="refreshWechatHealth">
              <div class="mini-status-dot" :class="stats.wechat_online ? 'green' : 'red'"></div>
              <div class="mini-status-info">
                <div class="mini-status-label">企业微信</div>
                <div class="mini-status-text">{{ stats.wechat_online ? '已连接' : '未连接' }}</div>
              </div>
              <img class="mini-status-icon" :src="iconWechatStatus" alt="企业微信状态" />
            </div>
          </el-tooltip>
          <el-tooltip :content="stats.erp_error || 'ERP 服务正常'" placement="left" :disabled="stats.erp_online">
            <div class="mini-status-card" :class="stats.erp_online ? 'online' : 'offline'">
              <div class="mini-status-dot" :class="stats.erp_online ? 'green' : 'red'"></div>
              <div class="mini-status-info">
                <div class="mini-status-label">ERP 服务</div>
                <div class="mini-status-text">{{ stats.erp_online ? '运行中' : '未启动' }}</div>
              </div>
              <img class="mini-status-icon" :src="iconErpStatus" alt="ERP 服务状态" />
            </div>
          </el-tooltip>
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
            <el-button type="primary" link size="small" @click="router.push('/system-center')">查看全部 →</el-button>
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
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
  import { ref, computed, onMounted, onUnmounted } from 'vue'
  import { useRouter } from 'vue-router'
  import { useUserStore } from '@/stores/user'
  import { Top, Bottom } from '@element-plus/icons-vue'
  import iconProduct from '@/assets/icons/product.svg'
  import iconOrder from '@/assets/icons/order.svg'
  import iconShipment from '@/assets/icons/shipment.svg'
  import iconWechatStatus from '@/assets/icons/企业微信.svg'
  import iconErpStatus from '@/assets/icons/数据连接_(1).svg'
  import request from '@/utils/request'

  const router = useRouter()
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
    wechat_error: '',
    erp_online: false,
    erp_error: '',
  })

const activities = computed(() => stats.value.recent_activities || [])

function updateGreeting() {
  const h = new Date().getHours()
  if (h >= 5 && h < 9) { greeting.value = '早安'; greetingSuffix.value = '祝你度过充实的一天' }
  else if (h >= 9 && h < 11) { greeting.value = '上午好'; greetingSuffix.value = '工作顺利' }
  else if (h >= 11 && h < 13) { greeting.value = '中午好'; greetingSuffix.value = '记得午休哦' }
  else if (h >= 13 && h < 18) { greeting.value = '下午好'; greetingSuffix.value = '继续加油' }
  else if (h >= 18 && h < 22) { greeting.value = '晚上好'; greetingSuffix.value = '辛苦了今天' }
  else { greeting.value = '夜深了'; greetingSuffix.value = '注意休息' }
}

const updateTime = () => {
  const now = new Date()
  currentTime.value = now.toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit' })
  currentDate.value = now.toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' })
  updateGreeting()
}

function calcTrend(today, yesterday) {
  if (yesterday === 0 && today === 0) return 0
  if (yesterday === 0) return 100
  return ((today - yesterday) / yesterday) * 100
}

function formatRevenue(val) {
  if (val >= 10000) return `¥${(val / 10000).toFixed(1)}万`
  if (val >= 1000) return `¥${(val / 1000).toFixed(1)}k`
  return `¥${val.toFixed(0)}`
}

const statCards = computed(() => {
  const s = stats.value
  return [
    { title: '在线产品', value: s.product_count.toLocaleString(), trend: null, trendLabel: '', icon: iconProduct, color: '#00B365' },
    { title: '今日订单', value: s.today_orders.toLocaleString(), trend: calcTrend(s.today_orders, s.yesterday_orders), trendLabel: '较昨日', icon: iconOrder, color: '#3370FF' },
    { title: '发货订单', value: s.today_shipments.toLocaleString(), trend: calcTrend(s.today_shipments, s.yesterday_shipments), trendLabel: '较昨日', icon: iconShipment, color: '#FF8800' }
  ]
})

// ---- 趋势图相关 ----
const chartRange = ref('7d')
const chartAnimKey = ref(0)

function polylineLength(dots) {
  let len = 0
  for (let i = 1; i < dots.length; i++) {
    const dx = dots[i].x - dots[i - 1].x
    const dy = dots[i].y - dots[i - 1].y
    len += Math.sqrt(dx * dx + dy * dy)
  }
  return len
}

const rangeOptions = [
  { label: '近一日', value: '1d' },
  { label: '近一周', value: '7d' },
  { label: '近一月', value: '30d' }
]

function switchRange(v) {
  chartRange.value = v
  chartAnimKey.value++
  fetchStats()
}

const chartData = computed(() => {
  const orders = stats.value.daily_orders || []
  const shipments = stats.value.daily_shipments || []
  return orders.map((o, i) => ({
    date: o.date,
    orders: o.count,
    shipments: shipments[i]?.count || 0
  }))
})

const chartMax = computed(() => {
  let m = 0
  chartData.value.forEach(d => { m = Math.max(m, d.orders, d.shipments) })
  return Math.max(m, 1)
})

const svgW = 800, svgH = 260, padL = 10, padR = 10, padT = 20, padB = 30
const gridCount = 4
const gridLines = computed(() => Array.from({ length: gridCount + 1 }, (_, i) => padT + (svgH - padT - padB) * (i / gridCount)))
const gridLinePercents = computed(() => gridLines.value.map(y => `${(y / svgH) * 100}%`))
const yAxisLabels = computed(() => {
  const max = chartMax.value
  return Array.from({ length: gridCount + 1 }, (_, i) => Math.round(max * (1 - i / gridCount)))
})

function toSvgPts(data, key) {
  const len = data.length
  if (!len) return []
  const areaW = svgW - padL - padR
  const areaH = svgH - padT - padB
  return data.map((d, i) => {
    const x = padL + (len === 1 ? areaW / 2 : (i / (len - 1)) * areaW)
    const y = padT + areaH - (d[key] / chartMax.value) * areaH
    return { x, y }
  })
}

const orderDots = computed(() => toSvgPts(chartData.value, 'orders'))
const shipmentDots = computed(() => toSvgPts(chartData.value, 'shipments'))
const orderPoints = computed(() => orderDots.value.map(p => `${p.x},${p.y}`).join(' '))
const shipmentPoints = computed(() => shipmentDots.value.map(p => `${p.x},${p.y}`).join(' '))

const orderLineLen = computed(() => polylineLength(orderDots.value))
const shipmentLineLen = computed(() => polylineLength(shipmentDots.value))

// ---- Hover tooltip ----
const chartWrapperRef = ref(null)
const hoverIdx = ref(-1)

const tooltipData = computed(() => {
  const idx = hoverIdx.value
  if (idx < 0 || idx >= chartData.value.length) return { date: '', orders: 0, shipments: 0 }
  const d = chartData.value[idx]
  const isHourly = chartRange.value === '1d'
  const weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
  let dateStr = d.date
  if (!isHourly) {
    const dt = new Date(d.date)
    dateStr = `${d.date} ${weekdays[dt.getDay()]}`
  }
  return { date: dateStr, orders: d.orders, shipments: d.shipments }
})

const tooltipStyle = computed(() => {
  const idx = hoverIdx.value
  if (idx < 0 || !chartWrapperRef.value) return {}
  const dots = orderDots.value
  if (!dots[idx]) return {}
  const rect = chartWrapperRef.value.getBoundingClientRect()
  const xRatio = dots[idx].x / svgW
  let left = xRatio * rect.width + 16
  if (left + 160 > rect.width) left = xRatio * rect.width - 176
  const yRatio = dots[idx].y / svgH
  let top = yRatio * rect.height - 20
  return { left: `${left}px`, top: `${top}px` }
})

function onChartMouseMove(e) {
  const svg = e.currentTarget
  const rect = svg.getBoundingClientRect()
  const mouseX = ((e.clientX - rect.left) / rect.width) * svgW
  const dots = orderDots.value
  if (!dots.length) { hoverIdx.value = -1; return }
  let closest = 0, minDist = Infinity
  dots.forEach((p, i) => {
    const dist = Math.abs(p.x - mouseX)
    if (dist < minDist) { minDist = dist; closest = i }
  })
  hoverIdx.value = minDist < 30 ? closest : -1
}

function onChartMouseLeave() { hoverIdx.value = -1 }

const xLabels = computed(() => {
  const data = chartData.value
  if (!data.length) return []
  const isHourly = chartRange.value === '1d'
  return data.map((d, i) => {
    if (isHourly) {
      if (i % 3 === 0) { const parts = d.date.split(' '); return parts[1] ? parts[1].slice(0, 5) : d.date }
      return ''
    }
    if (chartRange.value === '30d') {
      if (i % 5 === 0) return d.date.slice(5)
      return ''
    }
    return d.date.slice(5)
  })
})

const overviewItems = computed(() => {
  const s = stats.value
  return [
    { label: '今日订单', value: s.today_orders },
    { label: '今日发货', value: s.today_shipments },
    { label: '待审核订单', value: s.pending_orders },
    { label: '产品总数', value: s.product_count },
    { label: '本月营收', value: formatRevenue(s.month_revenue) },
  ]
})

async function fetchStats() {
  try {
    const res = await request.get('/api/dashboard/stats', { params: { range: chartRange.value } })
    if (res.data) Object.assign(stats.value, res.data)
  } catch (e) { console.error('fetchStats error', e) }
}

async function refreshWechatHealth() {
  try {
    const res = await request.post('/api/dashboard/refresh-wechat-health')
    const d = res.data || {}
    stats.value.wechat_online = !!d.online
    stats.value.wechat_error = d.online ? '' : (d.last_error || '')
  } catch { /* ignore */ }
}

onMounted(() => {
  updateTime()
  timer = setInterval(updateTime, 1000)
  fetchStats()
})

onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<style scoped>
/* 欢迎区域 */
.lark-dashboard { padding: 0; }

.lark-welcome-panel {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 24px 0 20px;
}

.welcome-title { font-size: 20px; font-weight: 600; color: var(--lark-text-primary); margin-bottom: 6px; }
.welcome-desc { font-size: 14px; color: var(--lark-text-secondary); }
.welcome-desc strong { color: var(--lark-primary); font-weight: 600; }
.date-widget { text-align: right; }
.date-time { font-size: 28px; font-weight: 700; color: var(--lark-text-primary); line-height: 1.2; }
.date-day { font-size: 14px; color: var(--lark-text-secondary); }

/* 核心指标卡片 */
.stat-cards-wrapper { margin-bottom: 24px; }

.lark-stat-card {
  background: var(--lark-bg-base);
  border-radius: var(--lark-radius-lg);
  padding: 14px 24px 20px;
  transition: transform 0.2s, box-shadow 0.2s;
  cursor: pointer;
  height: 100%;
}

.lark-stat-card:hover { transform: translateY(-2px); box-shadow: var(--lark-shadow-hover); }

.stat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.stat-name { font-size: 16px; font-weight: 600; color: var(--lark-text-regular); }

.stat-icon-wrap {
  width: 48px;
  height: 48px;
  padding: 10px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
}

.stat-icon {
  width: 28px;
  height: 28px;
  filter: brightness(0) invert(1);
  display: block;
  object-fit: contain;
}

.stat-body { margin-top: -6px; margin-bottom: 14px; }

.stat-number {
  font-size: 32px;
  font-weight: 700;
  color: var(--lark-text-primary);
  line-height: 1.1;
}

.stat-footer { display: flex; align-items: center; gap: 8px; font-size: 13px; }
.trend-label { color: var(--lark-text-secondary); }
.trend-value { display: flex; align-items: center; gap: 2px; font-weight: 500; }
.trend-value.is-up { color: #F54A45; }
.trend-value.is-down { color: #00B365; }

/* 服务状态卡片组 */
.status-card-group {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
}

.mini-status-card {
  flex: 1;
  background: var(--lark-bg-base);
  border-radius: var(--lark-radius-lg);
  cursor: pointer;
  padding: 16px 20px;
  display: flex;
  align-items: center;
  gap: 12px;
  transition: transform 0.2s, box-shadow 0.2s;
}

.mini-status-card:hover { transform: translateY(-1px); box-shadow: var(--lark-shadow-hover); }

.mini-status-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.mini-status-dot.green { background-color: #00B365; box-shadow: 0 0 0 3px rgba(0,179,101,0.15); }
.mini-status-dot.red { background-color: #F54A45; box-shadow: 0 0 0 3px rgba(245,74,69,0.15); }

.mini-status-info { display: flex; flex-direction: column; gap: 2px; flex: 1; }
.mini-status-label { font-size: 12px; color: var(--lark-text-secondary); line-height: 1; }
.mini-status-text { font-size: 16px; font-weight: 600; color: var(--lark-text-primary); line-height: 1.3; }
.mini-status-card.online .mini-status-text { color: #00B365; }
.mini-status-card.offline .mini-status-text { color: var(--lark-text-secondary); }
.mini-status-icon { width: 24px; height: 24px; flex-shrink: 0; object-fit: contain; }

.content-row { margin-bottom: 24px; }

.lark-panel {
  background: #fff;
  border-radius: var(--lark-radius-lg, 12px);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  height: 100%;
  display: flex;
  flex-direction: column;
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

.timeline-dot.urgent { background-color: #F56C6C; box-shadow: 0 0 0 3px #fde2e2; }
.timeline-dot.important { background-color: #E6A23C; box-shadow: 0 0 0 3px #faecd8; }
.timeline-dot.normal { background-color: #00B365; }

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
