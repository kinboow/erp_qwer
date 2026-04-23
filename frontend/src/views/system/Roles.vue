<template>
  <div class="lark-roles">
    <div class="lark-page-header">
      <div class="header-title">权限管理</div>
      <div class="header-desc">管理系统角色及其权限配置，超级管理员默认拥有所有权限</div>
    </div>

    <div class="lark-table-panel">
      <!-- 工具栏 -->
      <div class="lark-toolbar">
        <div class="toolbar-left">
          <div class="lark-search-input-wrap">
            <el-icon class="search-icon"><Search /></el-icon>
            <input
              v-model="searchKeyword"
              class="lark-input"
              placeholder="搜索角色名称或编码"
              @keyup.enter="handleSearch"
            />
            <el-icon v-if="searchKeyword" class="clear-icon" @click="clearSearch"><CircleClose /></el-icon>
          </div>
          <el-button class="lark-btn-secondary" @click="handleSearch">搜索</el-button>
        </div>
        <div class="toolbar-right">
          <el-button type="primary" :icon="Plus" @click="handleAdd">新建角色</el-button>
        </div>
      </div>

      <!-- 数据表格 -->
      <el-table
        :data="tableData"
        style="width: 100%"
        v-loading="loading"
        class="lark-table"
        :cell-style="{'border-bottom': '1px solid var(--lark-border-light)'}"
        :header-cell-style="{'border-bottom': '1px solid var(--lark-border-light)', 'background-color': 'var(--lark-bg-sidebar)', 'color': 'var(--lark-text-regular)', 'font-weight': '600'}"
      >
        <el-table-column label="角色名称" min-width="180">
          <template #default="{ row }">
            <div class="role-name-cell">
              <span class="role-name">{{ row.name }}</span>
              <span class="role-code">{{ row.code }}</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="描述" min-width="240" prop="description">
          <template #default="{ row }">
            <span class="desc-text">{{ row.description || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="关联用户" width="120">
          <template #default="{ row }">
            <span class="count-text">{{ row.user_count }} 人</span>
          </template>
        </el-table-column>

        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <div class="status-cell">
              <span class="status-dot" :class="row.status === 1 ? 'active' : 'inactive'"></span>
              <span class="status-text">{{ row.status === 1 ? '启用' : '停用' }}</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">
            <span class="time-text">{{ formatDate(row.created_at) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <div class="action-cell">
              <el-button link type="primary" class="lark-link" @click="handleEditPermissions(row)">配置权限</el-button>
              <el-divider direction="vertical" />
              <el-dropdown trigger="click" @command="(cmd) => handleMoreCommand(cmd, row)">
                <el-button link class="lark-link lark-link-more">
                  更多 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu class="lark-dropdown-menu">
                    <el-dropdown-item command="edit">
                      <el-icon><Edit /></el-icon>编辑信息
                    </el-dropdown-item>
                    <el-dropdown-item command="status">
                      <el-icon><Switch /></el-icon>{{ row.status === 1 ? '停用角色' : '启用角色' }}
                    </el-dropdown-item>
                    <el-dropdown-item command="delete" class="danger-text" :disabled="row.code === 'super_admin'">
                      <el-icon><Delete /></el-icon>删除角色
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="lark-pagination">
        <span class="total-text">共 {{ pagination.total }} 个角色</span>
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :total="pagination.total"
          :page-sizes="[10, 20, 50]"
          layout="sizes, prev, pager, next"
          @size-change="fetchData"
          @current-change="fetchData"
        />
      </div>
    </div>

    <!-- 新建/编辑角色弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogTitle"
      width="520px"
      @close="resetForm"
      destroy-on-close
      class="lark-dialog"
    >
      <div class="lark-form-container">
        <el-form :model="formData" :rules="rules" ref="formRef" label-position="top">
          <el-form-item label="角色名称" prop="name">
            <el-input v-model="formData.name" placeholder="如：运营管理员" />
          </el-form-item>
          <el-form-item label="角色编码" prop="code">
            <el-input v-model="formData.code" :disabled="isEdit" placeholder="如：ops_admin（创建后不可修改）" />
          </el-form-item>
          <el-form-item label="角色描述">
            <el-input v-model="formData.description" type="textarea" :rows="3" placeholder="简要描述角色的职责范围" />
          </el-form-item>
        </el-form>
      </div>
      <template #footer>
        <div class="lark-dialog-footer">
          <el-button class="lark-btn-secondary" @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" @click="handleSubmit" :loading="submitLoading">确定</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 配置权限弹窗 -->
    <el-dialog
      v-model="permDialogVisible"
      :title="`配置权限 - ${currentRole?.name || ''}`"
      width="600px"
      destroy-on-close
      class="lark-dialog"
    >
      <div class="perm-dialog-body">
        <div v-if="currentRole?.code === 'super_admin'" class="super-admin-notice">
          <el-icon color="#3370FF"><InfoFilled /></el-icon>
          <span>超级管理员默认拥有系统全部权限，无需单独配置</span>
        </div>

        <el-tree
          v-else
          ref="permTreeRef"
          :data="permissionTree"
          :props="treeProps"
          show-checkbox
          node-key="id"
          :default-checked-keys="currentPermIds"
          :default-expand-all="true"
          check-strictly
          class="perm-tree"
        />
      </div>
      <template #footer>
        <div class="lark-dialog-footer">
          <el-button class="lark-btn-secondary" @click="permDialogVisible = false">取消</el-button>
          <el-button
            v-if="currentRole?.code !== 'super_admin'"
            type="primary"
            @click="handleSavePermissions"
            :loading="permSaveLoading"
          >保存</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Search, Plus, Delete, CircleClose, ArrowDown,
  Switch, Edit, InfoFilled
} from '@element-plus/icons-vue'
import { getRoleList, createRole, updateRole, deleteRole, getRoleById, getPermissionTree } from '@/api/role'

const loading = ref(false)
const tableData = ref([])
const searchKeyword = ref('')
const pagination = reactive({ page: 1, pageSize: 10, total: 0 })

// 角色表单
const dialogVisible = ref(false)
const dialogTitle = ref('新建角色')
const isEdit = ref(false)
const submitLoading = ref(false)
const formRef = ref(null)
const formData = reactive({ id: null, name: '', code: '', description: '' })
const rules = {
  name: [{ required: true, message: '请输入角色名称', trigger: 'blur' }],
  code: [{ required: true, message: '请输入角色编码', trigger: 'blur' }]
}

// 权限配置
const permDialogVisible = ref(false)
const currentRole = ref(null)
const currentPermIds = ref([])
const permissionTree = ref([])
const permTreeRef = ref(null)
const permSaveLoading = ref(false)
const treeProps = { label: 'name', children: 'children' }

const fetchData = async () => {
  loading.value = true
  try {
    const res = await getRoleList({
      page: pagination.page,
      page_size: pagination.pageSize,
      keyword: searchKeyword.value
    })
    tableData.value = res.data.list
    pagination.total = res.data.total
  } catch (error) {
    console.error('获取角色列表失败:', error)
  } finally {
    loading.value = false
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

const handleAdd = () => {
  dialogTitle.value = '新建角色'
  isEdit.value = false
  dialogVisible.value = true
}

const handleMoreCommand = (command, row) => {
  if (command === 'edit') handleEditInfo(row)
  else if (command === 'status') handleStatusToggle(row)
  else if (command === 'delete') handleDelete(row)
}

const handleEditInfo = (row) => {
  dialogTitle.value = '编辑角色'
  isEdit.value = true
  formData.id = row.id
  formData.name = row.name
  formData.code = row.code
  formData.description = row.description || ''
  dialogVisible.value = true
}

const handleEditPermissions = async (row) => {
  currentRole.value = row
  try {
    const [roleRes, permRes] = await Promise.all([
      getRoleById(row.id),
      getPermissionTree()
    ])
    currentPermIds.value = roleRes.data.permissionIds || []
    permissionTree.value = permRes.data
    permDialogVisible.value = true
  } catch (error) {
    console.error('获取权限数据失败:', error)
  }
}

const handleSavePermissions = async () => {
  if (!permTreeRef.value) return
  permSaveLoading.value = true
  try {
    const checkedIds = permTreeRef.value.getCheckedKeys()
    const halfCheckedIds = permTreeRef.value.getHalfCheckedKeys()
    const permissionIds = [...checkedIds, ...halfCheckedIds]
    await updateRole(currentRole.value.id, { permissionIds })
    ElMessage.success('权限配置已保存')
    permDialogVisible.value = false
    fetchData()
  } catch (error) {
    console.error('保存权限失败:', error)
  } finally {
    permSaveLoading.value = false
  }
}

const handleStatusToggle = (row) => {
  const newStatus = row.status === 1 ? 0 : 1
  const actionText = newStatus === 1 ? '启用' : '停用'
  ElMessageBox.confirm(`确定要${actionText}角色 "${row.name}" 吗？`, '状态变更', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    customClass: 'lark-confirm'
  }).then(async () => {
    try {
      await updateRole(row.id, { status: newStatus })
      ElMessage.success(`已${actionText}`)
      fetchData()
    } catch (error) {
      console.error(error)
    }
  }).catch(() => {})
}

const handleDelete = (row) => {
  ElMessageBox.confirm(`删除角色后，关联用户将失去该角色的所有权限。确定删除 "${row.name}" 吗？`, '删除确认', {
    confirmButtonText: '删除',
    cancelButtonText: '取消',
    type: 'error',
    customClass: 'lark-confirm-danger'
  }).then(async () => {
    try {
      await deleteRole(row.id)
      ElMessage.success('已删除')
      fetchData()
    } catch (error) {
      console.error('删除失败:', error)
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
          await updateRole(formData.id, {
            name: formData.name,
            description: formData.description
          })
          ElMessage.success('保存成功')
        } else {
          await createRole(formData)
          ElMessage.success('创建成功')
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

const resetForm = () => {
  formData.id = null
  formData.name = ''
  formData.code = ''
  formData.description = ''
  if (formRef.value) formRef.value.resetFields()
}

const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit'
  })
}

onMounted(() => {
  fetchData()
})
</script>

<style scoped>
.lark-roles {
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

/* 搜索框 */
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

/* 表格 */
.lark-table {
  --el-table-border: none;
  --el-table-border-color: transparent;
}

:deep(.el-table::before) {
  display: none;
}

.role-name-cell {
  display: flex;
  flex-direction: column;
}

.role-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--lark-text-primary);
  margin-bottom: 2px;
}

.role-code {
  font-size: 12px;
  color: var(--lark-text-secondary);
  font-family: monospace;
}

.desc-text, .count-text, .time-text {
  font-size: 13px;
  color: var(--lark-text-regular);
}

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

/* 操作列 */
.action-cell {
  display: flex;
  align-items: center;
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

/* 对话框 */
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

/* 权限配置弹窗 */
.perm-dialog-body {
  max-height: 400px;
  overflow-y: auto;
}

.super-admin-notice {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px;
  background-color: var(--lark-primary-light);
  border-radius: var(--lark-radius);
  color: var(--lark-primary);
  font-size: 14px;
  font-weight: 500;
}

.perm-tree {
  padding: 8px 0;
}

:deep(.perm-tree .el-tree-node__content) {
  height: 36px;
  border-radius: var(--lark-radius-sm);
  margin-bottom: 2px;
}

:deep(.perm-tree .el-tree-node__content:hover) {
  background-color: var(--lark-bg-hover);
}
</style>
