<template>
  <el-container class="main-layout">
    <!-- 顶部导航 -->
    <el-header class="header">
      <div class="header-left">
        <el-icon class="logo-icon"><VideoCamera /></el-icon>
        <span class="logo-text">Stream V3</span>
        <el-tag type="success" effect="dark" size="small" class="version-tag">智能监控</el-tag>
      </div>
      
      <div class="header-right">
        <el-badge :value="unreadCount" :hidden="unreadCount === 0" class="notification-badge">
          <el-button circle @click="showNotifications">
            <el-icon><Bell /></el-icon>
          </el-button>
        </el-badge>
        
        <el-dropdown @command="handleCommand">
          <el-button circle>
            <el-icon><User /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="settings">系统设置</el-dropdown-item>
              <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </el-header>

    <el-container class="main-container">
      <!-- 侧边栏 -->
      <el-aside width="220px" class="sidebar">
        <el-menu
          :default-active="$route.path"
          router
          class="sidebar-menu"
          background-color="#304156"
          text-color="#bfcbd9"
          active-text-color="#409EFF"
        >
          <el-menu-item index="/dashboard">
            <el-icon><VideoCamera /></el-icon>
            <span>监控中心</span>
          </el-menu-item>
          
          <el-menu-item index="/streams">
            <el-icon><Monitor /></el-icon>
            <span>视频流管理</span>
          </el-menu-item>
          
          <el-menu-item index="/violations">
            <el-icon><Warning /></el-icon>
            <span>违规记录</span>
            <el-badge v-if="todayViolationCount > 0" :value="todayViolationCount" class="menu-badge" />
          </el-menu-item>
          
          <el-menu-item index="/vehicle-wash">
            <el-icon><Van /></el-icon>
            <span>车辆清洗</span>
          </el-menu-item>
          
          <el-menu-item index="/analytics">
            <el-icon><TrendCharts /></el-icon>
            <span>数据分析</span>
          </el-menu-item>
          
          <el-menu-item index="/reports">
            <el-icon><Document /></el-icon>
            <span>日报系统</span>
          </el-menu-item>
          
          <el-menu-item index="/settings">
            <el-icon><Setting /></el-icon>
            <span>系统设置</span>
          </el-menu-item>
        </el-menu>
        
        <!-- 系统状态 -->
        <div class="system-status">
          <div class="status-item">
            <el-icon :class="wsStore.isConnected ? 'connected' : 'disconnected'">
              <Connection />
            </el-icon>
            <span>{{ wsStore.isConnected ? '已连接' : '未连接' }}</span>
          </div>
          <div class="status-item">
            <el-icon><VideoPlay /></el-icon>
            <span>运行中: {{ runningCount }}</span>
          </div>
        </div>
      </el-aside>

      <!-- 主内容区 -->
      <el-main class="main-content">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useWebSocketStore } from '@/stores/websocket'
import { useStreamsStore } from '@/stores/streams'
import { useViolationsStore } from '@/stores/violations'

const route = useRoute()
const router = useRouter()
const wsStore = useWebSocketStore()
const streamsStore = useStreamsStore()
const violationsStore = useViolationsStore()

const unreadCount = computed(() => 0)
const todayViolationCount = computed(() => violationsStore.todayViolations.length)
const runningCount = computed(() => streamsStore.runningStreams.length)

const handleCommand = (command: string) => {
  if (command === 'settings') {
    router.push('/settings')
  } else if (command === 'logout') {
    // 处理退出登录
  }
}

const showNotifications = () => {
  // 显示通知面板
}

onMounted(() => {
  streamsStore.fetchStreams()
  // 不再这里获取违规记录，由各页面自行获取
})
</script>

<style scoped lang="scss">
.main-layout {
  height: 100vh;
  
  .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: #fff;
    border-bottom: 1px solid #e4e7ed;
    padding: 0 20px;
    
    .header-left {
      display: flex;
      align-items: center;
      gap: 12px;
      
      .logo-icon {
        font-size: 28px;
        color: #409EFF;
      }
      
      .logo-text {
        font-size: 20px;
        font-weight: 600;
        color: #303133;
      }
      
      .version-tag {
        margin-left: 8px;
      }
    }
    
    .header-right {
      display: flex;
      align-items: center;
      gap: 16px;
      
      .notification-badge {
        margin-right: 8px;
      }
    }
  }
  
  .main-container {
    height: calc(100vh - 60px);
    
    .sidebar {
      background: #304156;
      display: flex;
      flex-direction: column;
      
      .sidebar-menu {
        flex: 1;
        border-right: none;
        
        .menu-badge {
          margin-left: auto;
          margin-right: 8px;
        }
      }
      
      .system-status {
        padding: 16px;
        border-top: 1px solid #1f2d3d;
        
        .status-item {
          display: flex;
          align-items: center;
          gap: 8px;
          color: #bfcbd9;
          font-size: 13px;
          margin-bottom: 8px;
          
          &:last-child {
            margin-bottom: 0;
          }
          
          .connected {
            color: #67c23a;
          }
          
          .disconnected {
            color: #f56c6c;
          }
        }
      }
    }
    
    .main-content {
      background: #f0f2f5;
      padding: 20px;
      overflow-y: auto;
    }
  }
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
