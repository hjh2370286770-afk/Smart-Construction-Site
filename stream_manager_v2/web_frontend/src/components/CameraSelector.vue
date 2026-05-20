<template>
  <div class="camera-selector">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>视频流管理</span>
        </div>
      </template>
      
      <!-- 摄像头列表 -->
      <div class="camera-list">
        <el-select 
          v-model="selectedCamera" 
          placeholder="选择摄像头"
          @change="handleCameraChange"
          style="width: 100%"
        >
          <el-option-group
            v-for="site in camerasBySite"
            :key="site.siteId"
            :label="site.siteName"
          >
            <el-option
              v-for="cam in site.cameras"
              :key="cam.id"
              :label="`${cam.name} (${cam.status || '离线'})`"
              :value="cam.id"
            >
              <div class="camera-option">
                <span>{{ cam.name }}</span>
                <el-tag :type="cam.status === 'running' ? 'success' : 'info'" size="small">
                  {{ cam.status || '离线' }}
                </el-tag>
              </div>
            </el-option>
          </el-option-group>
        </el-select>
      </div>
      
      <!-- 检测器选择 -->
      <div class="detector-select" v-if="selectedCamera">
        <el-divider content-position="left">检测方案</el-divider>
        
        <el-form label-width="80px">
          <el-form-item label="检测器">
            <el-select 
              v-model="selectedDetector" 
              placeholder="选择检测器"
              @change="handleDetectorChange"
              style="width: 100%"
            >
              <el-option-group
                v-for="category in detectorsByCategory"
                :key="category.category"
                :label="getCategoryLabel(category.category)"
              >
                <el-option
                  v-for="det in category.detectors"
                  :key="det.id"
                  :label="det.name"
                  :value="det.id"
                >
                  <div class="detector-option">
                    <span>{{ det.name }}</span>
                    <el-tooltip :content="det.description" placement="top">
                      <el-icon><InfoFilled /></el-icon>
                    </el-tooltip>
                  </div>
                </el-option>
              </el-option-group>
            </el-select>
          </el-form-item>
          
          <el-form-item label="检测配置" v-if="selectedDetector">
            <el-input
              v-model="detectorConfigJson"
              type="textarea"
              :rows="3"
              placeholder="检测器配置 (JSON)"
            />
          </el-form-item>
        </el-form>
      </div>
      
      <!-- 操作按钮 -->
      <div class="action-buttons" v-if="selectedCamera">
        <el-button 
          type="primary" 
          @click="startDetection"
          :loading="loading"
          :disabled="!selectedDetector"
        >
          <el-icon><VideoPlay /></el-icon>
          开始检测
        </el-button>
        <el-button 
          type="danger" 
          @click="stopDetection"
          :disabled="!selectedDetector"
        >
          <el-icon><VideoPause /></el-icon>
          停止检测
        </el-button>
        <el-button @click="openSettings">
          <el-icon><Setting /></el-icon>
          高级设置
        </el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { 
  InfoFilled, 
  VideoPlay, 
  VideoPause, 
  Setting 
} from '@element-plus/icons-vue'
import { api } from '@/api'

// 事件
const emit = defineEmits<{
  'camera-change': [cameraId: string]
  'detector-change': [detectorId: string, config: object]
  'start': [cameraId: string, detectorId: string, config: object]
  'stop': []
}>()

// 状态
const loading = ref(false)
const selectedCamera = ref<string>('')
const selectedDetector = ref<string>('')
const detectorConfigJson = ref<string>('{}')
const cameras = ref<any[]>([])
const detectors = ref<any[]>([])

// 摄像头按工地分组
const camerasBySite = computed(() => {
  const siteMap = new Map<string, { siteId: string; siteName: string; cameras: any[] }>()
  
  for (const cam of cameras.value) {
    const siteId = cam.site_id || 'unknown'
    const siteName = cam.site_name || '未知工地'
    
    if (!siteMap.has(siteId)) {
      siteMap.set(siteId, { siteId, siteName, cameras: [] })
    }
    siteMap.get(siteId)!.cameras.push(cam)
  }
  
  return Array.from(siteMap.values())
})

// 检测器按类别分组
const detectorsByCategory = computed(() => {
  const categoryMap = new Map<string, { category: string; detectors: any[] }>()
  
  for (const det of detectors.value) {
    const category = det.category || 'other'
    
    if (!categoryMap.has(category)) {
      categoryMap.set(category, { category, detectors: [] })
    }
    categoryMap.get(category)!.detectors.push(det)
  }
  
  return Array.from(categoryMap.values())
})

// 获取类别标签
function getCategoryLabel(category: string): string {
  const labels: Record<string, string> = {
    ppe: 'PPE安全检测',
    wall: '墙面检测',
    vehicle: '车辆检测',
    tool: '刀具检测',
    other: '其他'
  }
  return labels[category] || '其他'
}

// 加载数据
async function loadCameras() {
  try {
    cameras.value = await api.getCameras()
  } catch (e) {
    console.error('加载摄像头失败:', e)
  }
}

async function loadDetectors() {
  try {
    const res = await api.getDetectors()
    detectors.value = res.detectors || []
  } catch (e) {
    console.error('加载检测器失败:', e)
  }
}

// 处理变更
function handleCameraChange(cameraId: string) {
  selectedDetector.value = ''
  detectorConfigJson.value = '{}'
  emit('camera-change', cameraId)
}

function handleDetectorChange(detectorId: string) {
  let config = {}
  try {
    config = JSON.parse(detectorConfigJson.value)
  } catch {}
  emit('detector-change', detectorId, config)
}

function openSettings() {
  ElMessage.info('高级设置功能开发中')
}

// 开始/停止检测
async function startDetection() {
  if (!selectedCamera.value || !selectedDetector.value) {
    ElMessage.warning('请选择摄像头和检测器')
    return
  }
  
  let config = {}
  try {
    config = JSON.parse(detectorConfigJson.value)
  } catch {
    ElMessage.error('检测器配置 JSON 格式错误')
    return
  }
  
  loading.value = true
  try {
    emit('start', selectedCamera.value, selectedDetector.value, config)
    ElMessage.success('开始检测')
  } finally {
    loading.value = false
  }
}

function stopDetection() {
  emit('stop')
  ElMessage.info('停止检测')
}

// 初始化
onMounted(() => {
  loadCameras()
  loadDetectors()
})

// 暴露方法
defineExpose({
  loadCameras,
  loadDetectors
})
</script>

<style scoped>
.camera-selector {
  margin-bottom: 20px;
}

.camera-option {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.detector-option {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.action-buttons {
  display: flex;
  gap: 10px;
  margin-top: 20px;
  justify-content: center;
}

.card-header {
  font-weight: bold;
  font-size: 16px;
}
</style>
