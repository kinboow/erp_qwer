<template>
  <div class="login-container">
    <div class="login-bg-overlay"></div>
    <div class="login-box">
      <div class="login-header">
        <div class="logo-circle">
          <el-icon :size="28" color="#fff"><Box /></el-icon>
        </div>
        <h2 class="login-title">Factory ERP</h2>
        <p class="login-subtitle">企业资源计划管理系统</p>
      </div>

      <el-form :model="loginForm" :rules="rules" ref="loginFormRef" class="login-form">
        <el-form-item prop="username">
          <el-input
            v-model="loginForm.username"
            placeholder="请输入用户名 / Admin"
            size="large"
            :prefix-icon="User"
            class="custom-input"
          />
        </el-form-item>
        <el-form-item prop="password">
          <el-input
            v-model="loginForm.password"
            type="password"
            placeholder="请输入密码 / admin123"
            size="large"
            :prefix-icon="Lock"
            show-password
            @keyup.enter="handleLogin"
            class="custom-input"
          />
        </el-form-item>

        <div class="login-options">
          <el-checkbox v-model="rememberMe">记住密码</el-checkbox>
          <el-link type="primary" underline="never">忘记密码？</el-link>
        </div>

        <el-form-item>
          <el-button
            type="primary"
            size="large"
            :loading="loading"
            @click="handleLogin"
            class="login-btn"
          >
            登录系统
          </el-button>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock, Box } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()
const loginFormRef = ref(null)
const loading = ref(false)
const rememberMe = ref(false)

const loginForm = reactive({
  username: 'admin',
  password: 'admin123'
})

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
}

onMounted(() => {
  localStorage.removeItem('token')
  localStorage.removeItem('userInfo')
  userStore.token = ''
  userStore.userInfo = {}
})

const handleLogin = async () => {
  if (!loginFormRef.value) return

  await loginFormRef.value.validate(async (valid) => {
    if (valid) {
      loading.value = true
      try {
        await userStore.login(loginForm)
        ElMessage({
          message: '登录成功，欢迎回来',
          type: 'success',
          duration: 2000
        })
        router.push('/')
      } catch (error) {
        console.error('登录失败:', error)
      } finally {
        loading.value = false
      }
    }
  })
}
</script>

<style scoped>
.login-container {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100vh;
  position: relative;
  background-image: url('https://images.unsplash.com/photo-1581091226825-a6a2a5aee158?ixlib=rb-4.0.3&auto=format&fit=crop&w=2000&q=80');
  background-size: cover;
  background-position: center;
}

.login-bg-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: linear-gradient(135deg, rgba(24, 43, 76, 0.85) 0%, rgba(53, 92, 125, 0.8) 100%);
  backdrop-filter: blur(4px);
}

.login-box {
  position: relative;
  width: 420px;
  padding: 40px;
  background: rgba(255, 255, 255, 0.95);
  border-radius: 12px;
  box-shadow: 0 15px 35px rgba(0, 0, 0, 0.2);
  z-index: 1;
  transition: transform 0.3s ease;
}

.login-box:hover {
  transform: translateY(-5px);
}

.login-header {
  text-align: center;
  margin-bottom: 35px;
}

.logo-circle {
  width: 60px;
  height: 60px;
  background: linear-gradient(135deg, #409EFF 0%, #3a8ee6 100%);
  border-radius: 50%;
  display: flex;
  justify-content: center;
  align-items: center;
  margin: 0 auto 15px;
  box-shadow: 0 4px 15px rgba(64, 158, 255, 0.3);
}

.login-title {
  color: #1f2f3d;
  font-size: 24px;
  font-weight: 600;
  margin: 0 0 5px;
  letter-spacing: 1px;
}

.login-subtitle {
  color: #909399;
  font-size: 13px;
  margin: 0;
}

.login-form {
  margin-top: 20px;
}

:deep(.custom-input .el-input__wrapper) {
  background-color: #f5f7fa;
  box-shadow: none !important;
  border: 1px solid #e4e7ed;
  transition: all 0.3s;
  padding: 0 15px;
}

:deep(.custom-input .el-input__wrapper:hover),
:deep(.custom-input .el-input__wrapper.is-focus) {
  background-color: #fff;
  border-color: #409EFF;
  box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.1) !important;
}

.login-options {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding: 0 5px;
}

.login-btn {
  width: 100%;
  height: 44px;
  font-size: 16px;
  font-weight: 500;
  letter-spacing: 2px;
  border-radius: 6px;
  background: linear-gradient(to right, #409EFF, #3a8ee6);
  border: none;
  transition: all 0.3s ease;
}

.login-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 15px rgba(64, 158, 255, 0.3);
}

.login-btn:active {
  transform: translateY(0);
}
</style>
