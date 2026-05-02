<template>
  <div class="login-container">
    <!-- 左侧图片区 -->
    <div class="login-left">
      <div class="login-left-overlay"></div>
      <div class="login-left-content">
        <img src="/logo-white.png" alt="logo" class="login-logo" />
        <h1 class="login-slogan">协途AI</h1>
        <p class="login-slogan-sub">智能化企业管理，让协作更高效</p>
      </div>
    </div>

    <!-- 右侧表单区 -->
    <div class="login-right">
      <div class="login-box">
        <div class="login-header">
          <h2 class="login-title">欢迎登录</h2>
          <p class="login-subtitle">请输入您的账号信息</p>
        </div>

        <el-form :model="loginForm" :rules="rules" ref="loginFormRef" class="login-form">
          <el-form-item prop="username">
            <el-input
              v-model="loginForm.username"
              placeholder="请输入用户名"
              size="large"
              :prefix-icon="User"
              class="custom-input"
            />
          </el-form-item>
          <el-form-item prop="password">
            <el-input
              v-model="loginForm.password"
              type="password"
              placeholder="请输入密码"
              size="large"
              :prefix-icon="Lock"
              show-password
              @keyup.enter="handleLogin"
              class="custom-input"
            />
          </el-form-item>

          <div class="login-options">
            <el-checkbox v-model="rememberMe">记住密码</el-checkbox>
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

        <div class="login-footer">© 2025 协途AI · All rights reserved</div>
      </div>
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
  height: 100vh;
  width: 100vw;
  overflow: hidden;
}

/* ---------- 左侧图片区 ---------- */
.login-left {
  flex: 1;
  position: relative;
  background-image: url('/login-bg.jpg');
  background-size: cover;
  background-position: center;
  display: flex;
  align-items: center;
  justify-content: center;
}

.login-left-overlay {
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, rgba(24, 43, 76, 0.82) 0%, rgba(53, 92, 125, 0.75) 100%);
  backdrop-filter: blur(2px);
}

.login-left-content {
  position: relative;
  z-index: 1;
  text-align: center;
  color: #fff;
}

.login-logo {
  width: 80px;
  height: 80px;
  object-fit: contain;
  margin-bottom: 10px;
  filter: drop-shadow(0 4px 12px rgba(0, 0, 0, 0.25));
}

.login-slogan {
  font-size: 44px;
  font-weight: 700;
  letter-spacing: 8px;
  margin: 0 0 14px;
  text-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}

.login-slogan-sub {
  font-size: 20px;
  opacity: 0.85;
  margin: 0;
  letter-spacing: 2px;
}

/* ---------- 右侧表单区 ---------- */
.login-right {
  width: 480px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #fff;
}

.login-box {
  width: 360px;
}

.login-header {
  margin-bottom: 32px;
}

.login-title {
  color: #1f2f3d;
  font-size: 26px;
  font-weight: 700;
  margin: 0 0 8px;
  letter-spacing: 1px;
}

.login-subtitle {
  color: #909399;
  font-size: 14px;
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
  height: 46px;
  font-size: 16px;
  font-weight: 500;
  letter-spacing: 3px;
  border-radius: 8px;
  background: linear-gradient(135deg, #409EFF 0%, #3a8ee6 100%);
  border: none;
  transition: all 0.3s ease;
}

.login-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(64, 158, 255, 0.35);
}

.login-btn:active {
  transform: translateY(0);
}

.login-footer {
  text-align: center;
  margin-top: 40px;
  font-size: 12px;
  color: #c0c4cc;
}
</style>
