<template>
  <el-container class="app-container">
    <!-- 侧边栏 -->
    <el-aside width="200px" class="sidebar">
      <div class="logo">
        <el-icon :size="32"><VideoCamera /></el-icon>
        <span>安全监控</span>
      </div>
      
      <el-menu
        :default-active="activeMenu"
        router
        class="menu"
        background-color="#001529"
        text-color="#fff"
        active-text-color="#409eff"
      >
        <el-menu-item index="/">
          <el-icon><Monitor /></el-icon>
          <span>监控大屏</span>
        </el-menu-item>
        
        <el-menu-item index="/violations">
          <el-icon><Warning /></el-icon>
          <span>违规记录</span>
        </el-menu-item>
        
        <el-menu-item index="/test">
          <el-icon><Tools /></el-icon>
          <span>连接测试</span>
        </el-menu-item>
      </el-menu>
      
      <!-- WebSocket 状态 -->
      <div class="ws-status" :class="wsStatus">
        <el-icon v-if="wsStatus === 'connected'"><CircleCheck /></el-icon>
        <el-icon v-else-if="wsStatus === 'connecting'"><Loading /></el-icon>
        <el-icon v-else><CircleClose /></el-icon>
        <span>{{ wsStatusText }}</span>
      </div>
    </el-aside>
    
    <!-- 主内容区 -->
    <el-main class="main-content">
      <router-view />
    </el-main>
  </el-container>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useWebSocketStore } from '@/stores/websocket'

const route = useRoute()
const wsStore = useWebSocketStore()

const activeMenu = computed(() => route.path)

const wsStatus = computed(() => wsStore.status)

const wsStatusText = computed(() => {
  const map: Record<string, string> = {
    connected: '已连接',
    connecting: '连接中...',
    disconnected: '已断开'
  }
  return map[wsStore.status] || wsStore.status
})
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  background: #f0f2f5;
}

.app-container {
  height: 100vh;
}

.sidebar {
  background: #001529;
  display: flex;
  flex-direction: column;
}

.logo {
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: #fff;
  font-size: 18px;
  font-weight: 600;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.menu {
  flex: 1;
  border-right: none;
}

.ws-status {
  padding: 12px 20px;
  display: flex;
  align-items: center;
  gap: 8px;
  color: #fff;
  font-size: 13px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

.ws-status.connected {
  color: #67c23a;
}

.ws-status.connecting {
  color: #e6a23c;
}

.ws-status.disconnected {
  color: #f56c6c;
}

.main-content {
  padding: 0;
  overflow-y: auto;
  background: #f0f2f5;
}
</style>
