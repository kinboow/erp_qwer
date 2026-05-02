<template>
  <div class="lark-users">
    <div class="lark-page-header">
      <div class="header-title">组织架构</div>
      <div class="header-desc">管理企业内部员工、下游客户与企微群聊</div>
    </div>

    <div class="lark-table-panel">
      <el-tabs v-model="activeTab" class="lark-tabs" @tab-change="handleTabChange">
        <el-tab-pane label="员工管理" name="employees">
          <div class="lark-toolbar">
            <div class="toolbar-left">
              <div class="lark-search-input-wrap">
                <el-icon class="search-icon"><Search /></el-icon>
                <input
                  v-model="searchKeyword"
                  class="lark-input"
                  placeholder="搜索成员姓名、用户名或邮箱"
                  @keyup.enter="handleSearch"
                />
                <el-icon v-if="searchKeyword" class="clear-icon" @click="clearSearch"><CircleClose /></el-icon>
              </div>
              <el-button class="lark-btn-secondary" @click="handleSearch">搜索</el-button>
            </div>

            <div class="toolbar-right">
              <el-button class="lark-btn-secondary" :icon="Setting" @click="openEmployeeSettings">企微设定</el-button>
              <el-button type="primary" :icon="Plus" @click="handleAdd">添加成员</el-button>
            </div>
          </div>

          <el-table
            :data="tableData"
            style="width: 100%"
            v-loading="loading"
            class="lark-table"
            :cell-style="{'border-bottom': '1px solid var(--lark-border-light)'}"
            :header-cell-style="{'border-bottom': '1px solid var(--lark-border-light)', 'background-color': 'var(--lark-bg-sidebar)', 'color': 'var(--lark-text-regular)', 'font-weight': '600'}"
          >
            <el-table-column label="成员" min-width="240">
              <template #default="{ row }">
                <div class="user-cell">
                  <el-avatar :size="36" :src="row.avatar || 'https://cube.elemecdn.com/3/7c/3ea6beec64369c2642b92c6726f1epng.png'" />
                  <div class="user-detail">
                    <span class="user-name">{{ row.real_name }}</span>
                    <span class="user-account">{{ row.username }}</span>
                  </div>
                </div>
              </template>
            </el-table-column>

            <el-table-column label="联系方式" min-width="200">
              <template #default="{ row }">
                <div class="contact-cell">
                  <div class="contact-item">
                    <el-icon><Message /></el-icon>
                    <span>{{ row.email || '-' }}</span>
                  </div>
                  <div class="contact-item">
                    <el-icon><Phone /></el-icon>
                    <span>{{ row.phone || '-' }}</span>
                  </div>
                </div>
              </template>
            </el-table-column>

            <el-table-column label="角色标签" min-width="160">
              <template #default="{ row }">
                <div class="tags-wrapper">
                  <span
                    v-for="role in row.roles"
                    :key="role"
                    class="lark-tag"
                    :class="getRoleTagClass(role)"
                  >
                    {{ getRoleName(role) }}
                  </span>
                  <span v-if="!row.roles || row.roles.length === 0" class="empty-text">-</span>
                </div>
              </template>
            </el-table-column>

            <el-table-column label="账号状态" width="120">
              <template #default="{ row }">
                <div class="status-cell">
                  <span class="status-dot" :class="row.status === 1 ? 'active' : 'inactive'"></span>
                  <span class="status-text">{{ row.status === 1 ? '使用中' : '已停用' }}</span>
                </div>
              </template>
            </el-table-column>

            <el-table-column label="最后活跃" width="160">
              <template #default="{ row }">
                <span class="time-text">{{ formatDate(row.last_login_time) || '-' }}</span>
              </template>
            </el-table-column>

            <el-table-column label="操作" width="160" fixed="right">
              <template #default="{ row }">
                <div class="action-cell">
                  <el-button link type="primary" class="lark-link" @click="handleEdit(row)">编辑</el-button>
                  <el-divider direction="vertical" />
                  <el-dropdown trigger="click" @command="(cmd) => handleMoreCommand(cmd, row)">
                    <el-button link class="lark-link lark-link-more">
                      更多 <el-icon class="el-icon--right"><arrow-down /></el-icon>
                    </el-button>
                    <template #dropdown>
                      <el-dropdown-menu class="lark-dropdown-menu">
                        <el-dropdown-item command="status">
                          <el-icon><Switch /></el-icon>{{ row.status === 1 ? '停用账号' : '启用账号' }}
                        </el-dropdown-item>
                        <el-dropdown-item command="password">
                          <el-icon><Key /></el-icon>重置密码
                        </el-dropdown-item>
                        <el-dropdown-item command="delete" class="danger-text" :disabled="row.username === 'admin'">
                          <el-icon><Delete /></el-icon>删除成员
                        </el-dropdown-item>
                      </el-dropdown-menu>
                    </template>
                  </el-dropdown>
                </div>
              </template>
            </el-table-column>
          </el-table>

          <div class="lark-pagination">
            <span class="total-text">共 {{ pagination.total }} 名成员</span>
            <el-pagination
              v-model:current-page="pagination.page"
              v-model:page-size="pagination.pageSize"
              :total="pagination.total"
              :page-sizes="[10, 20, 50, 100]"
              layout="total, sizes, prev, pager, next, jumper"
              @size-change="fetchData"
              @current-change="fetchData"
            />
          </div>
        </el-tab-pane>

        <el-tab-pane label="下游客户" name="customers">
          <div class="lark-toolbar">
            <div class="toolbar-left">
              <div class="lark-search-input-wrap">
                <el-icon class="search-icon"><Search /></el-icon>
                <input
                  v-model="customerSearchKeyword"
                  class="lark-input"
                  placeholder="搜索客户名称、编号、联系人、地址等"
                  @keyup.enter="handleCustomerSearch"
                />
                <el-icon v-if="customerSearchKeyword" class="clear-icon" @click="clearCustomerSearch"><CircleClose /></el-icon>
              </div>
              <el-button class="lark-btn-secondary" @click="handleCustomerSearch">搜索</el-button>
            </div>

            <div class="toolbar-right">
              <el-popover placement="bottom-end" trigger="click" :show-arrow="true">
                <template #reference>
                  <el-button :icon="Setting">列设置</el-button>
                </template>
                <div class="col-setting-panel">
                  <div class="col-setting-header">
                    <span>显示列</span>
                    <el-button link type="primary" size="small" @click="resetCustomerColumns">重置</el-button>
                  </div>
                  <el-checkbox-group v-model="visibleCustomerCols" class="col-setting-list">
                    <el-checkbox
                      v-for="col in allCustomerColumns"
                      :key="col.prop"
                      :label="col.prop"
                      :value="col.prop"
                    >{{ col.label }}</el-checkbox>
                  </el-checkbox-group>
                </div>
              </el-popover>
              <el-button :icon="Refresh" @click="handleSyncCustomers" :loading="customerSyncing">刷新</el-button>
            </div>
          </div>

          <el-table
            :data="customerTableData"
            style="width: 100%"
            v-loading="customerLoading"
            class="lark-table"
            :cell-style="{'border-bottom': '1px solid var(--lark-border-light)'}"
            :header-cell-style="{'border-bottom': '1px solid var(--lark-border-light)', 'background-color': 'var(--lark-bg-sidebar)', 'color': 'var(--lark-text-regular)', 'font-weight': '600'}"
          >
            <template v-for="col in activeCustomerColumns" :key="col.prop">
              <el-table-column
                v-if="col.prop === 'status'"
                :label="col.label"
                :prop="col.prop"
                :width="col.width"
                :min-width="col.minWidth"
                :sortable="!!col.sortable"
                align="center"
              >
                <template #default="{ row }">
                  <el-tag :type="getCustomerStatusType(row)" size="small">
                    {{ getCustomerStatusText(row) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column
                v-else-if="col.prop === 'nature'"
                :label="col.label"
                :prop="col.prop"
                :width="col.width"
                :min-width="col.minWidth"
                :sortable="!!col.sortable"
                show-overflow-tooltip
              >
                <template #default="{ row }">
                  {{ parseNature(row.nature) }}
                </template>
              </el-table-column>
              <el-table-column
                v-else-if="col.prop === 'credit_limit'"
                :label="col.label"
                :prop="col.prop"
                :width="col.width"
                :min-width="col.minWidth"
                :sortable="!!col.sortable"
                align="right"
              >
                <template #default="{ row }">
                  {{ row.credit_limit != null ? Number(row.credit_limit).toLocaleString() : '-' }}
                </template>
              </el-table-column>
              <el-table-column
                v-else-if="col.prop === 'wechat_rooms'"
                :label="col.label"
                :min-width="col.minWidth || 200"
              >
                <template #default="{ row }">
                  <div class="tags-wrapper">
                    <span
                      v-for="room in (row.wechat_rooms || []).slice(0, 3)"
                      :key="`${row.id}-${room.room_id}`"
                      class="lark-tag tag-blue"
                    >{{ room.room_name || room.room_id }}</span>
                    <span v-if="(row.wechat_rooms || []).length > 3" class="empty-text">+{{ row.wechat_rooms.length - 3 }}</span>
                    <span v-if="!row.wechat_rooms || row.wechat_rooms.length === 0" class="empty-text">-</span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column
                v-else
                :label="col.label"
                :prop="col.prop"
                :width="col.width"
                :min-width="col.minWidth"
                :sortable="!!col.sortable"
                show-overflow-tooltip
              />
            </template>
            <el-table-column label="操作" width="180" fixed="right">
              <template #default="{ row }">
                <div class="action-cell compact">
                  <el-tooltip v-if="row.status !== 1" content="ERP未启用，不可绑定" placement="top">
                    <el-button link type="info" class="lark-link" disabled>绑定</el-button>
                  </el-tooltip>
                  <el-button v-else link type="primary" class="lark-link" @click="handleCustomerBind(row)">绑定</el-button>
                  <el-button link type="primary" class="lark-link" @click="handleCustomerDetail(row)">详情</el-button>
                  <el-button link type="primary" class="lark-link" @click="handleViewOrders(row)">关联订单</el-button>
                </div>
              </template>
            </el-table-column>
          </el-table>

          <div class="lark-pagination">
            <span class="total-text">共 {{ customerPagination.total }} 位客户</span>
            <el-pagination
              v-model:current-page="customerPagination.page"
              v-model:page-size="customerPagination.pageSize"
              :total="customerPagination.total"
              :page-sizes="[20, 50, 100, 200]"
              layout="total, sizes, prev, pager, next, jumper"
              @size-change="fetchCustomerData"
              @current-change="fetchCustomerData"
            />
          </div>
        </el-tab-pane>

        <el-tab-pane label="企微群聊" name="wechat-rooms">
          <div style="padding: 8px 0;">
            <MonitoredRooms />
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- 弹窗：飞书风格表单 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogTitle"
      width="520px"
      @close="resetForm"
      destroy-on-close
      class="lark-dialog"
      :show-close="true"
    >
      <div class="lark-form-container">
        <el-form :model="formData" :rules="rules" ref="formRef" label-position="top">
          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item label="姓名" prop="real_name">
                <el-input v-model="formData.real_name" placeholder="请输入真实姓名" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="登录账号" prop="username">
                <el-input v-model="formData.username" :disabled="isEdit" placeholder="建议使用拼音缩写" />
              </el-form-item>
            </el-col>

            <el-col :span="24" v-if="!isEdit">
              <el-form-item label="初始密码" prop="password">
                <el-input v-model="formData.password" type="password" show-password placeholder="设置初始密码" />
              </el-form-item>
            </el-col>

            <el-col :span="12">
              <el-form-item label="手机号码" prop="phone">
                <el-input v-model="formData.phone" placeholder="选填" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="工作邮箱" prop="email">
                <el-input v-model="formData.email" placeholder="选填" />
              </el-form-item>
            </el-col>

            <el-col :span="24">
              <el-form-item label="所属角色" prop="role_ids">
                <el-select v-model="formData.role_ids" multiple placeholder="请选择角色" style="width: 100%">
                  <el-option
                    v-for="role in roleOptions"
                    :key="role.id"
                    :label="role.name"
                    :value="role.id"
                  />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>
        </el-form>
      </div>
      <template #footer>
        <div class="lark-dialog-footer">
          <el-button class="lark-btn-secondary" @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" @click="handleSubmit" :loading="submitLoading">确定</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 绑定群聊弹窗 -->
    <el-dialog
      v-model="bindDialogVisible"
      title="绑定企微群聊"
      width="520px"
      destroy-on-close
    >
      <div class="bind-dialog-info">
        <span class="bind-label">客户：</span>
        <span class="bind-value">{{ bindTarget.customer_name }}</span>
        <el-tag v-if="bindTarget.erp_customer_id" size="small" style="margin-left:8px;">{{ bindTarget.erp_customer_id }}</el-tag>
      </div>
      <el-form label-position="top" style="margin-top:12px;">
        <el-form-item label="关联企微群">
          <el-select
            v-model="bindRoomIds"
            multiple
            filterable
            clearable
            collapse-tags
            collapse-tags-tooltip
            placeholder="请选择要关联的企微群"
            style="width: 100%"
            :loading="wechatRoomLoading"
            loading-text="正在加载群聊列表…"
            no-data-text="暂无群聊数据"
            :disabled="!hasBoundWechatInstance"
          >
            <el-option
              v-for="room in wechatRoomOptions"
              :key="room.room_id"
              :label="room.room_name"
              :value="room.room_id"
            />
          </el-select>
          <div class="wechat-room-hint">
            <template v-if="hasBoundWechatInstance">
              <span>当前实例：{{ wechatBoundInstance.name || wechatBoundInstance.wxid }}</span>
              <span v-if="!wechatRoomLoading && wechatRoomOptions.length === 0">，暂未获取到群聊</span>
            </template>
            <template v-else>
              请先在"企微配置"中绑定当前企业微信实例
            </template>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="bindDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleBindSubmit" :loading="bindLoading">保存</el-button>
      </template>
    </el-dialog>

    <!-- 客户详情弹窗 -->
    <el-dialog
      v-model="detailDialogVisible"
      title="客户详情"
      width="640px"
      destroy-on-close
    >
      <el-descriptions :column="2" border size="default" class="customer-detail-desc">
        <el-descriptions-item label="ERP编号">{{ detailData.erp_customer_id || '-' }}</el-descriptions-item>
        <el-descriptions-item label="客户名称">{{ detailData.customer_name || '-' }}</el-descriptions-item>
        <el-descriptions-item label="简码">{{ detailData.short_code || '-' }}</el-descriptions-item>
        <el-descriptions-item label="联系人">{{ detailData.contact_person || '-' }}</el-descriptions-item>
        <el-descriptions-item label="手机">{{ detailData.phone || '-' }}</el-descriptions-item>
        <el-descriptions-item label="固定电话">{{ detailData.telephone || '-' }}</el-descriptions-item>
        <el-descriptions-item label="地址" :span="2">{{ detailData.address || '-' }}</el-descriptions-item>
        <el-descriptions-item label="收货地址" :span="2">{{ detailData.shipping_address || '-' }}</el-descriptions-item>
        <el-descriptions-item label="收货电话">{{ detailData.shipping_phone || '-' }}</el-descriptions-item>
        <el-descriptions-item label="邮箱">{{ detailData.email || '-' }}</el-descriptions-item>
        <el-descriptions-item label="所属公司">{{ detailData.company_name || '-' }}</el-descriptions-item>
        <el-descriptions-item label="业务员">{{ detailData.salesperson || '-' }}</el-descriptions-item>
        <el-descriptions-item label="客户类型">{{ detailData.customer_type || '-' }}</el-descriptions-item>
        <el-descriptions-item label="客户性质">{{ parseNature(detailData.nature) }}</el-descriptions-item>
        <el-descriptions-item label="信用额度">{{ detailData.credit_limit != null ? Number(detailData.credit_limit).toLocaleString() : '-' }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="getCustomerStatusType(detailData)" size="small">
            {{ getCustomerStatusText(detailData) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="关联群聊" :span="2">
          <div class="tags-wrapper" v-if="detailData.wechat_rooms && detailData.wechat_rooms.length">
            <span v-for="room in detailData.wechat_rooms" :key="room.room_id" class="lark-tag tag-blue">
              {{ room.room_name || room.room_id }}
            </span>
          </div>
          <span v-else class="empty-text">-</span>
        </el-descriptions-item>
        <el-descriptions-item label="备注" :span="2">{{ detailData.remark || '-' }}</el-descriptions-item>
        <el-descriptions-item label="同步时间">{{ formatDateTime(detailData.synced_at) }}</el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ formatDateTime(detailData.created_at) }}</el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button @click="detailDialogVisible = false">关闭</el-button>
        <el-button type="primary" @click="handleViewOrders(detailData)">查看关联订单</el-button>
      </template>
    </el-dialog>

    <!-- 企微设定：员工账号弹窗 -->
    <el-dialog
      v-model="empSettingVisible"
      title="企微设定 — 标记员工账号"
      width="640px"
      destroy-on-close
    >
      <div style="margin-bottom:12px;color:var(--lark-text-secondary);font-size:13px;">
        以下为所有客户群中的成员（已去重）。勾选的账号将被标记为员工，其在监听群聊中发送的消息将不被系统处理（日志仍保留）。
      </div>
      <div v-if="empMembersLoading" v-loading="true" style="min-height:120px;"></div>
      <template v-else>
        <div style="margin-bottom:8px;">
          <div class="lark-search-input-wrap" style="width:100%;">
            <el-icon class="search-icon"><Search /></el-icon>
            <input v-model="empSearchKw" class="lark-input" placeholder="搜索昵称或ID" />
            <el-icon v-if="empSearchKw" class="clear-icon" @click="empSearchKw = ''"><CircleClose /></el-icon>
          </div>
        </div>
        <el-table
          :data="filteredEmpMembers"
          max-height="400"
          class="lark-table"
          @selection-change="onEmpSelectionChange"
          ref="empTableRef"
          row-key="wxid"
          size="small"
        >
          <el-table-column type="selection" width="45" reserve-selection />
          <el-table-column label="头像" width="60">
            <template #default="{ row }">
              <el-avatar :size="28" :src="row.avatar || undefined">
                <el-icon :size="14"><User /></el-icon>
              </el-avatar>
            </template>
          </el-table-column>
          <el-table-column prop="nickname" label="昵称" min-width="140" />
          <el-table-column prop="wxid" label="企微ID" min-width="180">
            <template #default="{ row }">
              <span style="font-size:11px;font-family:monospace;color:var(--lark-text-secondary);">{{ row.wxid }}</span>
            </template>
          </el-table-column>
        </el-table>
        <div style="margin-top:8px;font-size:12px;color:var(--lark-text-secondary);">
          已选 {{ empSelectedWxids.length }} / {{ empAllMembers.length }} 人
        </div>
      </template>
      <template #footer>
        <el-button @click="empSettingVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSaveEmployees" :loading="empSaving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Search, Plus, Delete, Key, CircleClose,
  Message, Phone, ArrowDown, Switch, Refresh, Setting, User
} from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'
import { getUserList, createUser, updateUser, deleteUser, getUserRoleOptions } from '@/api/user'
import { getCustomerList, createCustomer, updateCustomer, deleteCustomer, syncCustomersFromErp, getPreference, savePreference } from '@/api/customer'
import { getInstances, getListeners, getRoomList, syncRooms, getWechatGlobalConfig, getCustomerRoomMembers, getEmployeeAccounts, saveEmployeeAccounts } from '@/api/wechat'
import MonitoredRooms from './MonitoredRooms.vue'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const activeTab = ref(route.meta.tab || 'employees')
const loading = ref(false)
const tableData = ref([])
const searchKeyword = ref('')
const pagination = reactive({
  page: 1,
  pageSize: 10,
  total: 0
})

const dialogVisible = ref(false)
const dialogTitle = ref('添加成员')
const isEdit = ref(false)
const submitLoading = ref(false)
const formRef = ref(null)
const formData = reactive({
  id: null,
  username: '',
  password: '',
  real_name: '',
  email: '',
  phone: '',
  status: 1,
  role_ids: []
})
const roleOptions = ref([])

const customerLoading = ref(false)
const customerSyncing = ref(false)
const customerTableData = ref([])
const customerSearchKeyword = ref('')
const customerPagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
})

// 客户表全部列定义
const allCustomerColumns = [
  { prop: 'erp_customer_id', label: 'ERP编号', width: 100, sortable: true },
  { prop: 'customer_name', label: '客户名称', minWidth: 105, sortable: true },
  { prop: 'short_code', label: '简码', width: 90, sortable: true },
  { prop: 'contact_person', label: '联系人', width: 100 },
  { prop: 'phone', label: '手机', width: 130 },
  { prop: 'telephone', label: '固定电话', width: 130 },
  { prop: 'address', label: '地址', minWidth: 220 },
  { prop: 'shipping_address', label: '收货地址', minWidth: 180 },
  { prop: 'shipping_phone', label: '收货电话', width: 130 },
  { prop: 'salesperson', label: '业务员', width: 90, sortable: true },
  { prop: 'customer_type', label: '客户类型', width: 100, sortable: true },
  { prop: 'nature', label: '客户性质', width: 120 },
  { prop: 'credit_limit', label: '信用额度', width: 110, sortable: true },
  { prop: 'email', label: '邮箱', width: 160 },
  { prop: 'company_name', label: '所属公司', minWidth: 150 },
  { prop: 'remark', label: '备注', minWidth: 140 },
  { prop: 'wechat_rooms', label: '关联群聊', minWidth: 200 },
  { prop: 'synced_at', label: '同步时间', width: 160, sortable: true },
  { prop: 'status', label: '状态', width: 110, sortable: true },
]

// 默认显示的列
const defaultVisibleCols = [
  'erp_customer_id', 'customer_name', 'short_code', 'phone',
  'address', 'credit_limit', 'remark', 'wechat_rooms', 'status'
]

// 列设置（从数据库加载，变更时保存到数据库）
const PREF_KEY = 'customer_visible_cols'
const visibleCustomerCols = ref([...defaultVisibleCols])
let _colsLoaded = false

const loadVisibleCols = async () => {
  try {
    const res = await getPreference(PREF_KEY)
    const val = res.data?.value
    if (val) {
      visibleCustomerCols.value = JSON.parse(val)
    }
  } catch {}
  _colsLoaded = true
}

watch(visibleCustomerCols, (val) => {
  if (!_colsLoaded) return
  savePreference(PREF_KEY, JSON.stringify(val)).catch(() => {})
}, { deep: true })

const activeCustomerColumns = computed(() =>
  allCustomerColumns.filter(col => visibleCustomerCols.value.includes(col.prop))
)

const resetCustomerColumns = () => {
  visibleCustomerCols.value = [...defaultVisibleCols]
}

const getCustomerStatusText = (row) => {
  const erpOn = row.status === 1
  const hasBind = row.wechat_rooms && row.wechat_rooms.length > 0
  if (erpOn && hasBind) return '正常'
  if (erpOn && !hasBind) return '未绑定群聊'
  if (!erpOn && hasBind) return '异常'
  return '停用'
}

const getCustomerStatusType = (row) => {
  const erpOn = row.status === 1
  const hasBind = row.wechat_rooms && row.wechat_rooms.length > 0
  if (erpOn && hasBind) return 'success'
  if (erpOn && !hasBind) return 'warning'
  if (!erpOn && hasBind) return 'danger'
  return 'info'
}

const parseNature = (val) => {
  if (!val) return '-'
  try {
    const arr = JSON.parse(val)
    return Array.isArray(arr) ? arr.join(', ') : val
  } catch {
    return val
  }
}

const snapshotAuth = () => ({
  roles: [...(userStore.roles || [])].sort().join(','),
  permissions: [...(userStore.permissions || [])].sort().join(',')
})

const syncAuthAndPromptReload = async (reason) => {
  const before = snapshotAuth()
  await userStore.fetchUserInfo().catch(() => {})
  const after = snapshotAuth()
  if (before.roles === after.roles && before.permissions === after.permissions) return

  try {
    await ElMessageBox.confirm(
      `你的账号权限已更新（${reason}），建议立即刷新页面以应用最新权限。`,
      '权限已更新',
      {
        confirmButtonText: '立即刷新',
        cancelButtonText: '稍后',
        type: 'warning',
        customClass: 'lark-confirm'
      }
    )
    window.location.reload()
  } catch {
    ElMessage.warning('权限已更新，建议稍后手动刷新页面')
  }
}

const formatDateTime = (val) => {
  if (!val) return '-'
  try {
    const d = new Date(val)
    if (isNaN(d.getTime())) return val
    const pad = (n) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  } catch {
    return val
  }
}
// 绑定群聊弹窗
const bindDialogVisible = ref(false)
const bindLoading = ref(false)
const bindTarget = reactive({ id: null, customer_name: '', erp_customer_id: '' })
const bindRoomIds = ref([])

// 详情弹窗
const detailDialogVisible = ref(false)
const detailData = ref({})

const customerDialogVisible = ref(false)
const customerDialogTitle = ref('新增客户')
const customerSubmitLoading = ref(false)
const customerIsEdit = ref(false)
const customerFormRef = ref(null)
const wechatRoomLoading = ref(false)
const wechatBoundInstance = ref(null)
const wechatRoomOptions = ref([])
const hasBoundWechatInstance = computed(() => !!wechatBoundInstance.value?.wxid)
const customerFormData = reactive({
  id: null,
  customer_name: '',
  contact_person: '',
  phone: '',
  email: '',
  company_name: '',
  erp_customer_id: '',
  address: '',
  remark: '',
  status: 1,
  wechat_room_ids: []
})

const rules = {
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
  real_name: [{ required: true, message: '请输入姓名', trigger: 'blur' }]
}

const customerRules = {
  customer_name: [{ required: true, message: '请输入客户名称', trigger: 'blur' }]
}

const fetchData = async () => {
  loading.value = true
  try {
    const res = await getUserList({
      page: pagination.page,
      page_size: pagination.pageSize,
      keyword: searchKeyword.value
    })
    tableData.value = res.data.list
    pagination.total = res.data.total
  } catch (error) {
    console.error('获取失败:', error)
  } finally {
    loading.value = false
  }
}

const fetchCustomerData = async () => {
  customerLoading.value = true
  try {
    const res = await getCustomerList({
      page: customerPagination.page,
      pageSize: customerPagination.pageSize,
      keyword: customerSearchKeyword.value
    })
    customerTableData.value = res.data.list
    customerPagination.total = res.data.total
  } catch (error) {
    console.error('获取客户失败:', error)
  } finally {
    customerLoading.value = false
  }
}

const loadBoundWechatInstance = async () => {
  try {
    const res = await getWechatGlobalConfig()
    const cfg = res.data || {}
    const wxid = (cfg.selected_wxid || '').trim()
    if (!wxid) {
      wechatBoundInstance.value = null
      return null
    }
    // 通过 wxid 查找 DB 中的实例记录以获取 id
    const instRes = await getInstances()
    const list = Array.isArray(instRes.data) ? instRes.data : []
    const matched = list.find(item => item.wxid === wxid)
    wechatBoundInstance.value = {
      id: matched?.id || null,
      wxid,
      name: matched?.name || wxid
    }
    return wechatBoundInstance.value
  } catch { /* ignore */ }
  wechatBoundInstance.value = null
  return null
}

const normalizeWechatRooms = (rooms) => {
  return (Array.isArray(rooms) ? rooms : [])
    .map(room => ({
      room_id: room.room_id || room.roomId || room.id || room.conversation_id || room.room_conversation_id || '',
      room_name: room.room_name || room.roomName || room.name || room.nickname || room.nick_name || '未命名群聊'
    }))
    .filter(room => room.room_id)
}

const extractWechatRooms = (rawRooms) => {
  if (Array.isArray(rawRooms)) {
    return rawRooms
  }
  if (rawRooms && typeof rawRooms === 'object') {
    return rawRooms.room_list || rawRooms.list || rawRooms.items || rawRooms.records || rawRooms.rooms || rawRooms.data || []
  }
  return []
}

const fetchSyncedWechatRooms = async (instanceId) => {
  const res = await getListeners({ instanceId, page: 1, pageSize: 500 })
  const list = Array.isArray(res.data?.list) ? res.data.list : []
  return list.map(item => ({
    room_id: item.room_id,
    room_name: item.room_name || '未命名群聊'
  })).filter(item => item.room_id)
}

const fetchWechatRoomsForCustomer = async () => {
  const bound = await loadBoundWechatInstance()

  if (!bound?.id) {
    wechatRoomOptions.value = []
    return
  }

  wechatRoomLoading.value = true
  try {
    const res = await getRoomList(bound.id)
    let normalizedRooms = normalizeWechatRooms(extractWechatRooms(res.data))

    if (normalizedRooms.length === 0) {
      await syncRooms(bound.id)
      normalizedRooms = await fetchSyncedWechatRooms(bound.id)
    }

    wechatRoomOptions.value = normalizedRooms
  } catch (error) {
    wechatRoomOptions.value = []
    ElMessage.error(error?.response?.data?.message || error?.message || '获取企微群列表失败')
  } finally {
    wechatRoomLoading.value = false
  }
}

const handleSearch = () => {
  pagination.page = 1
  fetchData()
}

const clearSearch = () => {
  searchKeyword.value = ''
  handleSearch()
}

const handleCustomerSearch = () => {
  customerPagination.page = 1
  fetchCustomerData()
}

const clearCustomerSearch = () => {
  customerSearchKeyword.value = ''
  handleCustomerSearch()
}

const handleSyncCustomers = async () => {
  customerSyncing.value = true
  try {
    const res = await syncCustomersFromErp()
    const d = res.data || {}
    ElMessage.success(`客户同步完成：共 ${d.synced || 0} 个客户`)
    await fetchCustomerData()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '同步失败')
  } finally {
    customerSyncing.value = false
  }
}

const getRoleName = (role) => {
  const map = {
    super_admin: '超级管理员',
    admin: '管理员',
    user: '普通成员'
  }
  return map[role] || role
}

const getRoleTagClass = (role) => {
  if (role === 'super_admin') return 'tag-red'
  if (role === 'admin') return 'tag-orange'
  return 'tag-blue'
}

const handleAdd = () => {
  dialogTitle.value = '添加成员'
  isEdit.value = false
  dialogVisible.value = true
}

const handleCustomerAdd = async () => {
  customerDialogTitle.value = '新增客户'
  customerIsEdit.value = false
  resetCustomerForm()
  customerDialogVisible.value = true
  fetchWechatRoomsForCustomer()
}

const handleEdit = (row) => {
  dialogTitle.value = '编辑成员信息'
  isEdit.value = true
  formData.id = row.id
  formData.username = row.username
  formData.real_name = row.real_name
  formData.email = row.email
  formData.phone = row.phone
  formData.status = row.status
  formData.role_ids = Array.isArray(row.role_ids) ? [...row.role_ids] : []
  dialogVisible.value = true
}

const fetchRoleOptions = async () => {
  try {
    const res = await getUserRoleOptions()
    roleOptions.value = Array.isArray(res.data) ? res.data : []
  } catch (error) {
    roleOptions.value = []
    console.error('获取角色选项失败:', error)
  }
}

const handleMoreCommand = (command, row) => {
  if (command === 'status') {
    handleStatusToggle(row)
  } else if (command === 'password') {
    handleResetPwd(row)
  } else if (command === 'delete') {
    handleDelete(row)
  }
}

const handleStatusToggle = async (row) => {
  const newStatus = row.status === 1 ? 0 : 1
  const actionText = newStatus === 1 ? '启用' : '停用'

  ElMessageBox.confirm(`确定要${actionText}员工 "${row.real_name}" 的账号吗？`, '状态变更', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    customClass: 'lark-confirm'
  }).then(async () => {
    try {
      await updateUser(row.id, { status: newStatus })
      ElMessage.success(`已${actionText}`)
      if (Number(row.id) === Number(userStore.userInfo?.id)) {
        if (newStatus === 0) {
          ElMessage.warning('当前账号已被停用，将自动退出登录')
          await userStore.logout()
          return
        }
        await syncAuthAndPromptReload('账号状态变更')
      }
      fetchData()
    } catch (error) {
      console.error(error)
    }
  }).catch(() => {})
}

const handleResetPwd = (row) => {
  ElMessageBox.prompt(`请为 "${row.real_name}" 设置新密码`, '重置密码', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    inputPattern: /.{6,}/,
    inputErrorMessage: '密码长度不能小于6位',
    inputType: 'password',
    customClass: 'lark-confirm'
  }).then(() => {
    ElMessage.success('密码重置成功')
  }).catch(() => {})
}

const handleDelete = (row) => {
  ElMessageBox.confirm(`删除后该成员将无法登录系统。确定删除 "${row.real_name}" 吗？`, '删除确认', {
    confirmButtonText: '删除',
    cancelButtonText: '取消',
    type: 'error',
    customClass: 'lark-confirm-danger'
  }).then(async () => {
    try {
      await deleteUser(row.id)
      ElMessage.success('已删除')
      fetchData()
    } catch (error) {
      console.error('删除失败:', error)
    }
  }).catch(() => {})
}

const handleCustomerEdit = async (row) => {
  customerDialogTitle.value = '编辑客户'
  customerIsEdit.value = true
  customerFormData.id = row.id
  customerFormData.customer_name = row.customer_name
  customerFormData.contact_person = row.contact_person
  customerFormData.phone = row.phone
  customerFormData.email = row.email
  customerFormData.company_name = row.company_name
  customerFormData.erp_customer_id = row.erp_customer_id || ''
  customerFormData.address = row.address
  customerFormData.remark = row.remark
  customerFormData.status = row.status
  customerFormData.wechat_room_ids = (row.wechat_rooms || []).map(item => item.room_id)
  customerDialogVisible.value = true
  fetchWechatRoomsForCustomer()
}

const handleCustomerBind = async (row) => {
  bindTarget.id = row.id
  bindTarget.customer_name = row.customer_name
  bindTarget.erp_customer_id = row.erp_customer_id || ''
  bindRoomIds.value = (row.wechat_rooms || []).map(r => r.room_id)
  bindDialogVisible.value = true
  fetchWechatRoomsForCustomer()
}

const handleBindSubmit = async () => {
  bindLoading.value = true
  try {
    const rooms = bindRoomIds.value.map(roomId => {
      const room = wechatRoomOptions.value.find(r => r.room_id === roomId)
      return {
        instance_id: wechatBoundInstance.value?.id,
        room_id: roomId,
        room_name: room?.room_name || ''
      }
    })
    await updateCustomer(bindTarget.id, { wechat_rooms: rooms })
    ElMessage.success('绑定成功')
    bindDialogVisible.value = false
    fetchCustomerData()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '绑定失败')
  } finally {
    bindLoading.value = false
  }
}

const handleCustomerDetail = (row) => {
  detailData.value = { ...row }
  detailDialogVisible.value = true
}

const handleViewOrders = (row) => {
  detailDialogVisible.value = false
  router.push({ path: '/sales', query: { customer: row.customer_name } })
}

const handleCustomerDelete = (row) => {
  ElMessageBox.confirm(`确定删除客户 "${row.customer_name}" 吗？`, '删除确认', {
    confirmButtonText: '删除',
    cancelButtonText: '取消',
    type: 'error',
    customClass: 'lark-confirm-danger'
  }).then(async () => {
    try {
      await deleteCustomer(row.id)
      ElMessage.success('已删除')
      fetchCustomerData()
    } catch (error) {
      console.error('删除客户失败:', error)
    }
  }).catch(() => {})
}

const handleSubmit = async () => {
  if (!formRef.value) return

  await formRef.value.validate(async (valid) => {
    if (valid) {
      submitLoading.value = true
      try {
        if (isEdit.value) {
          const isSelf = Number(formData.id) === Number(userStore.userInfo?.id)
          await updateUser(formData.id, {
            real_name: formData.real_name,
            email: formData.email,
            phone: formData.phone,
            role_ids: formData.role_ids
          })
          ElMessage.success('保存成功')
          if (isSelf) {
            await syncAuthAndPromptReload('角色变更')
          }
        } else {
          await createUser(formData)
          ElMessage.success('添加成功')
        }
        dialogVisible.value = false
        fetchData()
      } catch (error) {
        console.error('提交失败:', error)
      } finally {
        submitLoading.value = false
      }
    }
  })
}

const handleCustomerSubmit = async () => {
  if (!customerFormRef.value) return

  await customerFormRef.value.validate(async (valid) => {
    if (valid) {
      customerSubmitLoading.value = true
      try {
        const payload = {
          customer_name: customerFormData.customer_name,
          contact_person: customerFormData.contact_person,
          phone: customerFormData.phone,
          email: customerFormData.email,
          company_name: customerFormData.company_name,
          erp_customer_id: customerFormData.erp_customer_id,
          address: customerFormData.address,
          remark: customerFormData.remark,
          status: customerFormData.status,
          wechat_rooms: customerFormData.wechat_room_ids.map(roomId => {
            const room = wechatRoomOptions.value.find(item => item.room_id === roomId)
            return {
              instance_id: wechatBoundInstance.value?.id,
              room_id: roomId,
              room_name: room?.room_name || ''
            }
          }).filter(item => item.instance_id && item.room_id)
        }

        if (customerIsEdit.value) {
          await updateCustomer(customerFormData.id, payload)
          ElMessage.success('保存成功')
        } else {
          await createCustomer(payload)
          ElMessage.success('添加成功')
        }
        customerDialogVisible.value = false
        fetchCustomerData()
      } catch (error) {
        console.error('提交客户失败:', error)
      } finally {
        customerSubmitLoading.value = false
      }
    }
  })
}

const resetForm = () => {
  formData.id = null
  formData.username = ''
  formData.password = ''
  formData.real_name = ''
  formData.email = ''
  formData.phone = ''
  formData.status = 1
  formData.role_ids = []
  if (formRef.value) {
    formRef.value.resetFields()
  }
}

const resetCustomerForm = () => {
  customerFormData.id = null
  customerFormData.customer_name = ''
  customerFormData.contact_person = ''
  customerFormData.phone = ''
  customerFormData.email = ''
  customerFormData.company_name = ''
  customerFormData.erp_customer_id = ''
  customerFormData.address = ''
  customerFormData.remark = ''
  customerFormData.status = 1
  customerFormData.wechat_room_ids = []
  if (customerFormRef.value) {
    customerFormRef.value.resetFields()
  }
}

const handleTabChange = (tab) => {
  if (tab === 'employees') {
    router.push('/users')
    fetchData()
  } else if (tab === 'customers') {
    router.push('/customers')
    fetchCustomerData()
  } else if (tab === 'wechat-rooms') {
    router.push('/wechat-rooms')
  }
}

const formatDate = (dateStr) => {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'
  })
}

// ---------------------------------------------------------------------------
// 企微设定：员工账号管理
// ---------------------------------------------------------------------------
const empSettingVisible = ref(false)
const empMembersLoading = ref(false)
const empSaving = ref(false)
const empAllMembers = ref([])
const empSelectedWxids = ref([])
const empSearchKw = ref('')
const empTableRef = ref(null)

const filteredEmpMembers = computed(() => {
  if (!empSearchKw.value) return empAllMembers.value
  const kw = empSearchKw.value.toLowerCase()
  return empAllMembers.value.filter(m =>
    (m.nickname || '').toLowerCase().includes(kw) ||
    (m.wxid || '').toLowerCase().includes(kw)
  )
})

function onEmpSelectionChange(rows) {
  empSelectedWxids.value = rows.map(r => r.wxid)
}

async function openEmployeeSettings() {
  empSettingVisible.value = true
  empMembersLoading.value = true
  empSearchKw.value = ''
  empAllMembers.value = []
  empSelectedWxids.value = []

  try {
    // 同时拉取所有客户群成员 + 已保存的员工列表
    const [membersRes, savedRes] = await Promise.all([
      getCustomerRoomMembers(),
      getEmployeeAccounts()
    ])
    empAllMembers.value = membersRes.data || []
    const savedWxids = new Set((savedRes.data || []).map(a => a.wxid))

    // 等 nextTick 让表格渲染后再设置选中
    await new Promise(r => setTimeout(r, 100))
    if (empTableRef.value) {
      empAllMembers.value.forEach(m => {
        if (savedWxids.has(m.wxid)) {
          empTableRef.value.toggleRowSelection(m, true)
        }
      })
    }
  } catch (e) {
    ElMessage.error('加载成员列表失败: ' + (e?.response?.data?.message || e.message))
  } finally {
    empMembersLoading.value = false
  }
}

async function handleSaveEmployees() {
  empSaving.value = true
  try {
    const accounts = empAllMembers.value
      .filter(m => empSelectedWxids.value.includes(m.wxid))
      .map(m => ({ wxid: m.wxid, nickname: m.nickname }))
    await saveEmployeeAccounts(accounts)
    ElMessage.success(`已保存 ${accounts.length} 个员工账号`)
    empSettingVisible.value = false
  } catch (e) {
    ElMessage.error('保存失败: ' + (e?.response?.data?.message || e.message))
  } finally {
    empSaving.value = false
  }
}

onMounted(async () => {
  await fetchRoleOptions()
  loadBoundWechatInstance()
  await loadVisibleCols()
  if (route.query.keyword) {
    searchKeyword.value = String(route.query.keyword)
    activeTab.value = 'employees'
  }
  if (activeTab.value === 'customers') {
    fetchCustomerData()
  } else {
    fetchData()
  }
})
</script>

<style scoped>
.lark-users {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.lark-page-header {
  margin-bottom: 4px;
}

.header-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--lark-text-primary);
  margin-bottom: 6px;
}

.header-desc {
  font-size: 13px;
  color: var(--lark-text-secondary);
}

.lark-table-panel {
  background: var(--lark-bg-base);
  border-radius: var(--lark-radius-lg);
  padding: 20px 24px;
}

:deep(.lark-tabs .el-tabs__header) {
  margin-bottom: 18px;
}

/* 工具栏 */
.lark-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.toolbar-left, .toolbar-right {
  display: flex;
  gap: 12px;
  align-items: center;
}

.lark-btn-secondary {
  background-color: var(--lark-bg-base);
  border: 1px solid var(--lark-border);
  color: var(--lark-text-primary);
}

.lark-btn-secondary:hover {
  background-color: var(--lark-bg-hover);
  border-color: var(--lark-border);
  color: var(--lark-text-primary);
}

/* 飞书风格搜索框 */
.lark-search-input-wrap {
  display: flex;
  align-items: center;
  background-color: var(--lark-bg-base);
  border: 1px solid var(--lark-border);
  border-radius: var(--lark-radius-sm);
  padding: 0 12px;
  height: 32px;
  width: 260px;
  transition: all 0.2s;
}

.lark-search-input-wrap:focus-within {
  border-color: var(--lark-primary);
  box-shadow: 0 0 0 2px var(--lark-primary-light);
}

.lark-search-input-wrap .search-icon {
  color: var(--lark-text-secondary);
  margin-right: 8px;
}

.lark-input {
  border: none;
  background: transparent;
  outline: none;
  flex: 1;
  font-size: 14px;
  color: var(--lark-text-primary);
}

.clear-icon {
  color: var(--lark-text-disabled);
  cursor: pointer;
}

.clear-icon:hover {
  color: var(--lark-text-secondary);
}

/* 表格覆盖样式 */
.lark-table {
  --el-table-border: none;
  --el-table-border-color: transparent;
}

:deep(.el-table::before) {
  display: none;
}

/* 单元格内容样式 */
.user-cell {
  display: flex;
  align-items: center;
  gap: 12px;
}

.user-detail {
  display: flex;
  flex-direction: column;
}

.user-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--lark-text-primary);
  margin-bottom: 2px;
}

.user-account {
  font-size: 12px;
  color: var(--lark-text-secondary);
}

.contact-cell {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.contact-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--lark-text-regular);
}

/* 飞书风格标签 */
.tags-wrapper {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.lark-tag {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.tag-blue { background-color: #eef2ff; color: #3370FF; }
.tag-orange { background-color: #fff3e8; color: #FF8800; }
.tag-red { background-color: #fef0f0; color: #F54A45; }

/* 状态圆点 */
.status-cell {
  display: flex;
  align-items: center;
  gap: 6px;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

.status-dot.active { background-color: #00B365; }
.status-dot.inactive { background-color: var(--lark-text-disabled); }

.status-text {
  font-size: 13px;
  color: var(--lark-text-regular);
}

.time-text, .empty-text {
  font-size: 13px;
  color: var(--lark-text-regular);
}

/* 操作列 */
.action-cell {
  display: flex;
  align-items: center;
}

.action-cell.compact {
  gap: 0;
}

.action-cell.compact .lark-link {
  padding: 4px 4px;
  font-size: 13px;
}

.lark-link {
  font-size: 14px;
  font-weight: 500;
  padding: 4px 8px;
}

.lark-link-more {
  color: var(--lark-text-regular);
}

.lark-link-more:hover {
  color: var(--lark-primary);
}

/* 分页 */
.lark-pagination {
  margin-top: 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.total-text {
  font-size: 14px;
  color: var(--lark-text-secondary);
}

/* 对话框重写 */
:deep(.lark-dialog .el-dialog__header) {
  padding: 24px 24px 16px;
  margin: 0;
  border-bottom: none;
}

:deep(.lark-dialog .el-dialog__title) {
  font-size: 18px;
  font-weight: 600;
  color: var(--lark-text-primary);
}

:deep(.lark-dialog .el-dialog__body) {
  padding: 0 24px 20px;
}

:deep(.lark-dialog .el-dialog__footer) {
  padding: 16px 24px 24px;
  border-top: none;
}

/* 飞书表单标签居上 */
:deep(.lark-form-container .el-form-item__label) {
  padding-bottom: 4px;
  font-weight: 500;
  color: var(--lark-text-primary);
}

.lark-dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

.danger-text {
  color: #F54A45 !important;
}

/* 列设置面板 */
.col-setting-panel {
  max-height: 400px;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.col-setting-panel::-webkit-scrollbar {
  display: none;
}

.col-setting-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--lark-text-primary);
}

.col-setting-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.col-setting-list .el-checkbox {
  margin-right: 0;
  height: 28px;
}

/* 绑定弹窗客户信息 */
.bind-dialog-info {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  background: var(--lark-bg-subtle, #f7f8fa);
  border-radius: var(--lark-radius, 6px);
  font-size: 14px;
}
.bind-label {
  color: var(--lark-text-secondary);
}
.bind-value {
  font-weight: 600;
  color: var(--lark-text-primary);
}

/* 客户详情描述列表 */
:deep(.customer-detail-desc .el-descriptions__label) {
  width: 80px;
  font-weight: 500;
  padding: 8px 10px;
}

:deep(.customer-detail-desc .el-descriptions__content) {
  padding: 8px 10px;
}

/* 表头文字不换行，排序图标与文字同行 */
:deep(.lark-table .el-table__header th .cell) {
  white-space: nowrap;
  display: inline-flex;
  align-items: center;
}
</style>
