<template>
  <div class="dashboard">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1>监控大屏</h1>
      <el-button type="primary" @click="refreshData">
        <el-icon><Refresh /></el-icon>
        刷新
      </el-button>
    </div>
    
    <!-- 统计卡片 -->
    <el-row :gutter="20" class="stats-row">
      <el-col :xs="12" :sm="6" :md="6" :lg="6">
        <StatCard
          label="在线摄像头"
          :value="onlineCameras"
          icon="VideoCamera"
        />
      </el-col>
      <el-col :xs="12" :sm="6" :md="6" :lg="6">
        <StatCard
          label="当前人员"
          :value="totalPersons"
          icon="User"
        />
      </el-col>
      <el-col :xs="12" :sm="6" :md="6" :lg="6">
        <StatCard
          label="今日违规"
          :value="todayViolations"
          icon="Warning"
        />
      </el-col>
      <el-col :xs="12" :sm="6" :md="6" :lg="6">
        <StatCard
          label="合规率"
          :value="complianceRate + '%'"
          icon="CircleCheck"
        />
      </el-col>
    </el-row>
    
    <!-- 摄像头网格 -->
    <div class="section-header">
      <h2>实时监控</h2>
      <el-radio-group v-model="viewMode" size="small">
        <el-radio-button label="grid">网格</el-radio-button>
        <el-radio-button label="list">列表</el-radio-button>
      </el-radio-group>
    </div>
    
    <el-row :gutter="20" class="camera-grid">
      <el-col 
        v-for="camera in cameras" 
        :key="camera.id" 
        :xs="12" :sm="8" :md="6" :lg="4"
      >
        <CameraCard 
          :camera="camera" 
          @click="openCameraDetail(camera.id)"
        />
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useMonitorStore } from '@/stores/monitor'
import { useWebSocketStore } from '@/stores/websocket'
import StatCard from '@/components/StatCard.vue'
import CameraCard from '@/components/CameraCard.vue'

const router = useRouter()
const monitorStore = useMonitorStore()
const wsStore = useWebSocketStore()

const viewMode = ref('grid')

const cameras = computed(() => monitorStore.cameras)
const onlineCameras = computed(() => monitorStore.onlineCameras)
const totalCameras = computed(() => monitorStore.totalCameras)
const totalPersons = computed(() => monitorStore.totalPersons)
const todayViolations = computed(() => monitorStore.todayViolations)
const complianceRate = computed(() => monitorStore.complianceRate)

function refreshData() {
  monitorStore.fetchCameras()
  monitorStore.fetchStats()
}

function openCameraDetail(cameraId: string) {
  router.push(`/camera/${cameraId}`)
}

onMounted(() => {
  monitorStore.fetchCameras()
  monitorStore.fetchStats()
})
</script>

<style scoped>
.dashboard {
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.page-header h1 {
  margin: 0;
  font-size: 24px;
}

.stats-row {
  margin-bottom: 20px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 24px 0 16px;
}

.section-header h2 {
  margin: 0;
  font-size: 18px;
}

.camera-grid {
  margin-top: 16px;
}
</style>
