<template>
  <div class="monitored-rooms">
    <!-- 顶部工具栏 -->
    <div class="rooms-toolbar">
      <div class="toolbar-left">
        <div class="lark-search-input-wrap">
          <el-icon class="search-icon"><Search /></el-icon>
          <input
            v-model="searchKeyword"
            class="lark-input"
            placeholder="搜索群聊名称"
            @keyup.enter="applyFilter"
          />
          <el-icon v-if="searchKeyword" class="clear-icon" @click="searchKeyword = ''"><CircleClose /></el-icon>
        </div>
        <el-select v-model="filterType" placeholder="全部类型" clearable size="default" style="width: 140px;" @change="applyFilter">
          <el-option label="客户群" value="customer" />
          <el-option label="内部群" value="internal" />
          <el-option label="未分类" value="none" />
        </el-select>
      </div>
      <div class="toolbar-right">
        <el-tag type="info" effect="plain">共 {{ rooms.length }} 个群聊</el-tag>
        <el-button size="small" :icon="Refresh" @click="loadRooms" :loading="loading">刷新</el-button>
      </div>
    </div>

    <!-- 加载中 -->
    <div v-if="loading" v-loading="true" style="min-height: 200px;"></div>

    <!-- 空状态 -->
    <div v-else-if="rooms.length === 0" class="empty-hint">
      暂无群聊数据。请先在「外部配置 → 企业微信配置」中完成 API 连接与实例绑定。
    </div>

    <!-- 群聊列表 -->
    <div v-else class="room-list">
      <div
        v-for="room in filteredRooms"
        :key="room.room_id"
        class="room-card"
        :class="{
          expanded: expandedRoomId === room.room_id,
          'card-customer': room.is_customer,
          'card-internal': room.is_internal && !room.is_customer
        }"
      >
        <div class="room-header" @click="toggleRoom(room)">
          <div class="room-left">
            <div class="room-avatar" :class="getRoomAvatarClass(room)">
              <el-icon :size="20"><ChatDotRound /></el-icon>
            </div>
            <div class="room-info">
              <div class="room-name-row">
                <span class="room-name">{{ room.room_name || room.room_id }}</span>
                <el-tag v-if="room.member_count" size="small" type="info" effect="plain" round>{{ room.member_count }}人</el-tag>
              </div>
              <div class="room-tags">
                <!-- 客户群标签 -->
                <el-tag v-if="room.is_customer" size="small" type="success" effect="light">
                  客户群 · {{ room.customer?.customer_name }}
                </el-tag>
                <!-- 内部群标签 -->
                <el-tag v-if="room.is_internal" size="small" type="warning" effect="light">
                  内部群 · {{ internalTypeLabel(room.internal?.room_type) }}
                </el-tag>
                <!-- 未分类 -->
                <el-tag v-if="!room.is_customer && !room.is_internal" size="small" type="info" effect="plain">
                  未分类
                </el-tag>
                <span v-if="room.room_id" class="room-id-text">{{ room.room_id }}</span>
              </div>
            </div>
          </div>
          <div class="room-right">
            <!-- 操作按钮 -->
            <el-dropdown
              v-if="!room.is_customer"
              trigger="click"
              @command="(cmd) => handleRoomAction(cmd, room)"
              @click.stop
            >
              <el-button size="small" text @click.stop>
                <el-icon><Setting /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item v-if="!room.is_internal" command="set-shipping">设为发货群</el-dropdown-item>
                  <el-dropdown-item v-if="!room.is_internal" command="set-notification">设为通知群</el-dropdown-item>
                  <el-dropdown-item v-if="room.is_internal" command="unset-internal" divided>取消内部群</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-icon class="expand-icon" :class="{ rotated: expandedRoomId === room.room_id }">
              <ArrowDown />
            </el-icon>
          </div>
        </div>

        <!-- 成员面板 -->
        <transition name="slide">
          <div v-if="expandedRoomId === room.room_id" class="room-members-panel">
            <div v-if="memberLoading" v-loading="true" style="min-height: 60px;"></div>
            <div v-else-if="memberError" class="member-error">
              <el-icon><WarningFilled /></el-icon>
              {{ memberError }}
            </div>
            <div v-else-if="currentMembers.length === 0" class="member-empty">暂无成员信息</div>
            <div v-else class="member-grid">
              <div v-for="(m, idx) in currentMembers" :key="idx" class="member-item">
                <div class="member-avatar">
                  <img v-if="m.avatar || m.small_avatar" :src="m.avatar || m.small_avatar" alt="" class="member-avatar-img" />
                  <el-icon v-else :size="16"><User /></el-icon>
                </div>
                <div class="member-detail">
                  <div class="member-name">{{ m.realname || m.username || m.room_nickname || m.nickname || m.user_id || '未知' }}</div>
                  <div class="member-wxid">{{ m.acctid || m.user_id || '' }}<span v-if="m.mobile" class="member-mobile"> · {{ m.mobile }}</span></div>
                </div>
              </div>
            </div>
          </div>
        </transition>
      </div>

      <div v-if="filteredRooms.length === 0 && rooms.length > 0" class="empty-hint">
        没有符合条件的群聊
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ChatDotRound, Refresh, ArrowDown, User, WarningFilled,
  Search, CircleClose, Setting
} from '@element-plus/icons-vue'
import request from '@/utils/request'

const loading = ref(false)
const rooms = ref([])
const searchKeyword = ref('')
const filterType = ref('')
const expandedRoomId = ref(null)
const memberLoading = ref(false)
const memberError = ref('')
const memberCache = reactive({})

const INTERNAL_TYPE_LABELS = { shipping: '发货群', notification: '通知群' }

function internalTypeLabel(t) {
  return INTERNAL_TYPE_LABELS[t] || t || '未知'
}

function getRoomAvatarClass(room) {
  if (room.is_customer) return 'avatar-customer'
  if (room.is_internal) return 'avatar-internal'
  return 'avatar-default'
}

const filteredRooms = computed(() => {
  let list = rooms.value
  if (searchKeyword.value) {
    const kw = searchKeyword.value.toLowerCase()
    list = list.filter(r =>
      (r.room_name || '').toLowerCase().includes(kw) ||
      (r.room_id || '').toLowerCase().includes(kw) ||
      (r.customer?.customer_name || '').toLowerCase().includes(kw)
    )
  }
  if (filterType.value === 'customer') list = list.filter(r => r.is_customer)
  else if (filterType.value === 'internal') list = list.filter(r => r.is_internal)
  else if (filterType.value === 'none') list = list.filter(r => !r.is_customer && !r.is_internal)
  return list
})

const currentMembers = computed(() => {
  if (!expandedRoomId.value) return []
  return memberCache[expandedRoomId.value] || []
})

function applyFilter() { /* computed handles reactivity */ }

async function loadRooms() {
  loading.value = true
  try {
    const res = await request({ url: '/api/wechat/rooms/all-status', method: 'get' })
    rooms.value = res.data || []
  } catch (e) {
    ElMessage.error('加载群聊失败: ' + (e?.response?.data?.message || e.message))
  } finally {
    loading.value = false
  }
}

async function fetchMembers(roomId) {
  if (memberCache[roomId]) return
  memberLoading.value = true
  memberError.value = ''
  try {
    const res = await request({
      url: '/api/wechat/proxy/room-members',
      method: 'post',
      data: { room_id: roomId }
    })
    memberCache[roomId] = Array.isArray(res.data) ? res.data : []
  } catch (e) {
    memberError.value = e?.response?.data?.message || e.message || '获取群成员失败'
  } finally {
    memberLoading.value = false
  }
}

function toggleRoom(room) {
  if (expandedRoomId.value === room.room_id) {
    expandedRoomId.value = null
  } else {
    expandedRoomId.value = room.room_id
    fetchMembers(room.room_id)
  }
}

async function handleRoomAction(cmd, room) {
  if (cmd === 'set-shipping' || cmd === 'set-notification') {
    const isShipping = cmd === 'set-shipping'
    const label = isShipping ? '发货群' : '通知群'
    const roomType = isShipping ? 'shipping' : 'notification'
    try {
      await ElMessageBox.confirm(
        `确认将「${room.room_name || room.room_id}」设为${label}？`,
        '设为内部群',
        { confirmButtonText: '确定', cancelButtonText: '取消', type: 'info' }
      )
      await request({
        url: '/api/wechat/rooms/set-internal',
        method: 'post',
        data: { room_id: room.room_id, room_name: room.room_name, room_type: roomType }
      })
      ElMessage.success(`已设为${label}`)
      loadRooms()
    } catch (e) {
      if (e !== 'cancel' && e?.toString() !== 'cancel') {
        ElMessage.error(e?.response?.data?.message || e.message || '操作失败')
      }
    }
  } else if (cmd === 'unset-internal') {
    try {
      await ElMessageBox.confirm(
        `确认取消「${room.room_name || room.room_id}」的内部群标记？`,
        '取消内部群',
        { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
      )
      await request({
        url: '/api/wechat/rooms/unset-internal',
        method: 'post',
        data: { room_id: room.room_id }
      })
      ElMessage.success('已取消内部群')
      loadRooms()
    } catch (e) {
      if (e !== 'cancel' && e?.toString() !== 'cancel') {
        ElMessage.error(e?.response?.data?.message || e.message || '操作失败')
      }
    }
  }
}

onMounted(loadRooms)
</script>

<style scoped>
.monitored-rooms {
  margin-top: 0;
}

/* 工具栏 */
.rooms-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  gap: 12px;
  flex-wrap: wrap;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.lark-search-input-wrap {
  display: flex;
  align-items: center;
  background: var(--lark-bg-body, #f7f8fa);
  border: 1px solid var(--lark-border-light, #e5e6eb);
  border-radius: 8px;
  padding: 0 10px;
  height: 32px;
  width: 220px;
  transition: border-color 0.2s;
}

.lark-search-input-wrap:focus-within {
  border-color: var(--lark-primary, #3370ff);
}

.lark-search-input-wrap .search-icon {
  color: var(--lark-text-secondary);
  font-size: 14px;
  margin-right: 6px;
}

.lark-search-input-wrap .clear-icon {
  color: var(--lark-text-secondary);
  font-size: 14px;
  cursor: pointer;
  margin-left: 4px;
}

.lark-search-input-wrap .lark-input {
  border: none;
  outline: none;
  background: transparent;
  font-size: 13px;
  color: var(--lark-text-primary);
  flex: 1;
  min-width: 0;
}

/* 空状态 */
.empty-hint {
  padding: 40px;
  text-align: center;
  color: var(--lark-text-secondary, #8f959e);
  font-size: 14px;
}

/* 群聊列表 */
.room-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.room-card {
  background: var(--lark-bg-base, #fff);
  border-radius: 10px;
  border: 1.5px solid transparent;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  transition: all 0.2s;
  overflow: hidden;
}

.room-card:hover {
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}

.room-card.expanded {
  border-color: var(--lark-primary, #3370ff);
}

.room-card.card-customer {
  border-left: 3px solid #00b365;
}

.room-card.card-internal {
  border-left: 3px solid #ff8800;
}

/* 头部 */
.room-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  cursor: pointer;
  user-select: none;
}

.room-left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  flex: 1;
}

.room-avatar {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.room-avatar.avatar-customer {
  background: linear-gradient(135deg, #d4f5e2, #e8f8ef);
  color: #00b365;
}

.room-avatar.avatar-internal {
  background: linear-gradient(135deg, #fff0d6, #fff7e8);
  color: #ff8800;
}

.room-avatar.avatar-default {
  background: linear-gradient(135deg, #f0f0f5, #e8e8ed);
  color: var(--lark-text-secondary);
}

.room-info {
  min-width: 0;
  flex: 1;
}

.room-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.room-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--lark-text-primary, #1f2329);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.room-tags {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.room-id-text {
  font-size: 11px;
  color: var(--lark-text-disabled, #bbb);
  font-family: 'SF Mono', 'Menlo', monospace;
}

.room-right {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.expand-icon {
  transition: transform 0.25s;
  color: var(--lark-text-secondary);
  font-size: 14px;
}

.expand-icon.rotated {
  transform: rotate(180deg);
}

/* 成员面板 */
.room-members-panel {
  border-top: 1px solid var(--lark-border-light, #f0f0f0);
  padding: 14px 16px;
  background: var(--lark-bg-body, #f7f8fa);
}

.member-error {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #f54a45;
  font-size: 13px;
  padding: 8px 0;
}

.member-empty {
  text-align: center;
  color: var(--lark-text-secondary);
  font-size: 13px;
  padding: 12px 0;
}

.member-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 8px;
}

.member-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  background: var(--lark-bg-base, #fff);
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(0,0,0,0.03);
}

.member-avatar {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: #f0f0f0;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: var(--lark-text-secondary);
  overflow: hidden;
}

.member-avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 8px;
}

.member-detail {
  min-width: 0;
}

.member-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--lark-text-primary, #1f2329);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.member-wxid {
  font-size: 11px;
  color: var(--lark-text-secondary, #8f959e);
  font-family: 'SF Mono', 'Menlo', monospace;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 展开动画 */
.slide-enter-active, .slide-leave-active {
  transition: all 0.25s ease;
  max-height: 500px;
  overflow: hidden;
}

.slide-enter-from, .slide-leave-to {
  max-height: 0;
  padding-top: 0;
  padding-bottom: 0;
  opacity: 0;
}
</style>
