<template>
  <div class="vehicle-wash-page">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1>车辆清洗检测</h1>
      <el-button type="primary" @click="handleExport" :loading="exportLoading">
        <el-icon><Download /></el-icon>
        导出Excel
      </el-button>
    </div>

    <!-- 统计卡片 -->
    <el-row :gutter="20" class="stats-row">
      <el-col :xs="12" :sm="12" :md="6" :lg="6">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-icon blue">
            <el-icon><Van /></el-icon>
          </div>
          <div class="stat-content">
            <div class="stat-value">{{ stats.today_entries }}</div>
            <div class="stat-label">今日进场</div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="12" :md="6" :lg="6">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-icon green">
            <el-icon><Check /></el-icon>
          </div>
          <div class="stat-content">
            <div class="stat-value">{{ stats.today_exits }}</div>
            <div class="stat-label">今日出场</div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="12" :md="6" :lg="6">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-icon orange">
            <el-icon><Brush /></el-icon>
          </div>
          <div class="stat-content">
            <div class="stat-value">{{ stats.today_washed }}</div>
            <div class="stat-label">今日清洗</div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="12" :md="6" :lg="6">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-icon purple">
            <el-icon><Timer /></el-icon>
          </div>
          <div class="stat-content">
            <div class="stat-value">{{ stats.active_vehicles }}</div>
            <div class="stat-label">在场车辆</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 在场车辆 -->
    <el-card class="section-card" v-if="activeVehicles.length > 0">
      <template #header>
        <div class="card-header">
          <span>在场车辆 ({{ activeVehicles.length }})</span>
          <el-tag type="warning" v-if="activeVehicles.length > 0">实时</el-tag>
        </div>
      </template>
      <el-table :data="activeVehicles" size="small" stripe>
        <el-table-column prop="license_plate" label="车牌号" width="120">
          <template #default="{ row }">
            <el-tag size="large" type="primary">{{ row.license_plate }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="entry_time" label="进场时间" width="180" />
        <el-table-column prop="dwell_time" label="停留时间" width="120">
          <template #default="{ row }">
            <el-tag :type="getDwellTimeType(row.dwell_time)">
              {{ formatDwellTime(row.dwell_time) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="is_washed" label="清洗状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_washed ? 'success' : 'info'">
              {{ row.is_washed ? '已清洗' : '未清洗' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="wash_start_time" label="清洗开始" width="180">
          <template #default="{ row }">
            <span v-if="row.wash_start_time">{{ row.wash_start_time }}</span>
            <span v-else class="text-gray">-</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 筛选和记录列表 -->
    <el-card class="section-card">
      <template #header>
        <div class="card-header">
          <span>清洗记录</span>
          <div class="filter-bar">
            <el-date-picker
              v-model="dateRange"
              type="daterange"
              range-separator="至"
              start-placeholder="开始日期"
              end-placeholder="结束日期"
              size="small"
              @change="handleDateChange"
            />
            <el-input
              v-model="plateFilter"
              placeholder="车牌号筛选"
              size="small"
              clearable
              style="width: 150px"
              @change="loadRecords"
            />
            <el-select
              v-model="washedFilter"
              placeholder="清洗状态"
              size="small"
              clearable
              style="width: 120px"
              @change="loadRecords"
            >
              <el-option label="全部" value="" />
              <el-option label="已清洗" :value="true" />
              <el-option label="未清洗" :value="false" />
            </el-select>
            <el-select
              v-model="exitFilter"
              placeholder="出场状态"
              size="small"
              clearable
              style="width: 120px"
              @change="loadRecords"
            >
              <el-option label="全部" value="" />
              <el-option label="已出场" :value="true" />
              <el-option label="在场中" :value="false" />
            </el-select>
            <el-button type="primary" size="small" @click="loadRecords">
              <el-icon><Search /></el-icon>
              查询
            </el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="records"
        v-loading="loading"
        size="small"
        stripe
        border
      >
        <el-table-column type="index" label="序号" width="60" align="center" />
        <el-table-column prop="license_plate" label="车牌号" width="120" align="center">
          <template #default="{ row }">
            <el-tag size="large" :type="row.is_washed ? 'success' : 'primary'">
              {{ row.license_plate }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="entry_time" label="进场时间" width="170" />
        <el-table-column prop="exit_time" label="出场时间" width="170">
          <template #default="{ row }">
            <span v-if="row.exit_time">{{ row.exit_time }}</span>
            <el-tag v-else type="warning" size="small">在场中</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="dwell_time" label="停留时间" width="120" align="center">
          <template #default="{ row }">
            {{ formatDwellTime(row.dwell_time) }}
          </template>
        </el-table-column>
        <el-table-column prop="is_washed" label="是否清洗" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_washed ? 'success' : 'info'" size="small">
              {{ row.is_washed ? '是' : '否' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="wash_start_time" label="清洗开始" width="170">
          <template #default="{ row }">
            <span v-if="row.wash_start_time">{{ row.wash_start_time }}</span>
            <span v-else class="text-gray">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="wash_duration" label="清洗时长" width="120" align="center">
          <template #default="{ row }">
            <span v-if="row.wash_duration > 0">{{ formatDwellTime(row.wash_duration) }}</span>
            <span v-else class="text-gray">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="is_reentry" label="二次进场" width="90" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.is_reentry" type="warning" size="small">是</el-tag>
            <span v-else class="text-gray">否</span>
          </template>
        </el-table-column>
        <el-table-column prop="vehicle_id" label="车辆ID" width="90" align="center" />
      </el-table>

      <!-- 分页 -->
      <div class="pagination-bar">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[20, 50, 100]"
          :total="total"
          layout="total, sizes, prev, pager, next"
          @size-change="loadRecords"
          @current-change="loadRecords"
        />
      </div>
    </el-card>

    <!-- 统计图表 -->
    <el-row :gutter="20" class="charts-row">
      <el-col :xs="24" :sm="24" :md="12">
        <el-card class="chart-card">
          <template #header>
            <span>近7日趋势</span>
          </template>
          <div ref="dailyChartRef" class="chart-container"></div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="24" :md="12">
        <el-card class="chart-card">
          <template #header>
            <span>高频车辆TOP10</span>
          </template>
          <el-table :data="plateStats" size="small" stripe>
            <el-table-column type="index" label="排名" width="60" align="center" />
            <el-table-column prop="license_plate" label="车牌号" />
            <el-table-column prop="entry_count" label="进场次数" width="100" align="center" />
            <el-table-column prop="wash_count" label="清洗次数" width="100" align="center" />
            <el-table-column prop="avg_dwell_time" label="平均停留" width="120" align="center">
              <template #default="{ row }">
                {{ formatDwellTime(row.avg_dwell_time) }}
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { Van, Check, Brush, Timer, Search, Download } from '@element-plus/icons-vue'
import { vehicleWashApi } from '@/api'
import * as echarts from 'echarts'

// 统计数据
const stats = ref({
  total_records: 0,
  total_entries: 0,
  total_exits: 0,
  active_vehicles: 0,
  washed_count: 0,
  wash_rate: 0,
  avg_dwell_time: 0,
  today_entries: 0,
  today_exits: 0,
  today_washed: 0
})

// 记录列表
const records = ref<any[]>([])
const activeVehicles = ref<any[]>([])
const loading = ref(false)
const exportLoading = ref(false)

// 筛选条件
const dateRange = ref<[Date, Date] | null>(null)
const plateFilter = ref('')
const washedFilter = ref<boolean | ''>('')
const exitFilter = ref<boolean | ''>('')

// 分页
const currentPage = ref(1)
const pageSize = ref(20)
const total = ref(0)

// 图表
const dailyChartRef = ref<HTMLElement>()
let dailyChart: echarts.ECharts | null = null
const dailyStats = ref<any[]>([])
const plateStats = ref<any[]>([])

// 定时刷新
let refreshTimer: number | null = null

// 加载统计数据
const loadStats = async () => {
  try {
    const data = await vehicleWashApi.getStats()
    stats.value = data
  } catch (error) {
    console.error('加载统计失败:', error)
  }
}

// 加载记录
const loadRecords = async () => {
  loading.value = true
  try {
    const params: any = {
      limit: pageSize.value,
      offset: (currentPage.value - 1) * pageSize.value
    }

    if (dateRange.value && dateRange.value[0]) {
      params.start_date = formatDate(dateRange.value[0])
      params.end_date = formatDate(dateRange.value[1])
    }
    if (plateFilter.value) {
      params.plate = plateFilter.value
    }
    if (washedFilter.value !== '') {
      params.is_washed = washedFilter.value
    }
    if (exitFilter.value !== '') {
      params.has_exited = exitFilter.value
    }

    const data = await vehicleWashApi.getRecords(params)
    records.value = data
    total.value = data.length // 实际应该返回总数
  } catch (error) {
    console.error('加载记录失败:', error)
    ElMessage.error('加载记录失败')
  } finally {
    loading.value = false
  }
}

// 加载在场车辆
const loadActiveVehicles = async () => {
  try {
    const data = await vehicleWashApi.getActiveVehicles()
    activeVehicles.value = data
  } catch (error) {
    console.error('加载在场车辆失败:', error)
  }
}

// 加载每日统计
const loadDailyStats = async () => {
  try {
    const data = await vehicleWashApi.getDailyStats(7)
    dailyStats.value = data
    renderDailyChart()
  } catch (error) {
    console.error('加载每日统计失败:', error)
  }
}

// 加载车牌统计
const loadPlateStats = async () => {
  try {
    const data = await vehicleWashApi.getPlateStats(10)
    plateStats.value = data
  } catch (error) {
    console.error('加载车牌统计失败:', error)
  }
}

// 渲染每日图表
const renderDailyChart = () => {
  if (!dailyChartRef.value) return

  if (!dailyChart) {
    dailyChart = echarts.init(dailyChartRef.value)
  }

  const dates = dailyStats.value.map(d => d.date.substring(5)) // MM-DD
  const entries = dailyStats.value.map(d => d.entries)
  const exits = dailyStats.value.map(d => d.exits)
  const washed = dailyStats.value.map(d => d.washed)

  const option: echarts.EChartsOption = {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' }
    },
    legend: {
      data: ['进场', '出场', '清洗'],
      bottom: 0
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '15%',
      top: '10%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: dates
    },
    yAxis: {
      type: 'value',
      minInterval: 1
    },
    series: [
      {
        name: '进场',
        type: 'bar',
        data: entries,
        itemStyle: { color: '#409EFF' }
      },
      {
        name: '出场',
        type: 'bar',
        data: exits,
        itemStyle: { color: '#67C23A' }
      },
      {
        name: '清洗',
        type: 'bar',
        data: washed,
        itemStyle: { color: '#E6A23C' }
      }
    ]
  }

  dailyChart.setOption(option)
}

// 导出Excel
const handleExport = async () => {
  exportLoading.value = true
  try {
    const params: any = {}
    if (dateRange.value && dateRange.value[0]) {
      params.start_date = formatDate(dateRange.value[0])
      params.end_date = formatDate(dateRange.value[1])
    }
    if (plateFilter.value) {
      params.plate = plateFilter.value
    }

    const result = await vehicleWashApi.export(params)
    if (result.success && result.download_url) {
      // 下载文件
      const link = document.createElement('a')
      link.href = result.download_url
      link.download = result.file_path?.split('/').pop() || 'export.xlsx'
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      ElMessage.success('导出成功')
    } else {
      ElMessage.warning(result.message || '导出失败')
    }
  } catch (error) {
    console.error('导出失败:', error)
    ElMessage.error('导出失败')
  } finally {
    exportLoading.value = false
  }
}

// 日期变化
const handleDateChange = () => {
  currentPage.value = 1
  loadRecords()
}

// 格式化日期
const formatDate = (date: Date): string => {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

// 格式化停留时间
const formatDwellTime = (seconds: number): string => {
  if (!seconds || seconds <= 0) return '-'
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const secs = Math.floor(seconds % 60)
  if (hours > 0) {
    return `${hours}时${minutes}分`
  }
  return `${minutes}分${secs}秒`
}

// 停留时间类型（用于标签颜色）
const getDwellTimeType = (seconds: number): string => {
  if (!seconds) return 'info'
  const minutes = seconds / 60
  if (minutes < 3) return 'success'
  if (minutes < 10) return 'warning'
  return 'danger'
}

// 刷新所有数据
const refreshAll = () => {
  loadStats()
  loadRecords()
  loadActiveVehicles()
  loadDailyStats()
  loadPlateStats()
}

// 初始化
onMounted(() => {
  refreshAll()
  // 每30秒自动刷新
  refreshTimer = window.setInterval(() => {
    loadStats()
    loadActiveVehicles()
  }, 30000)

  // 窗口大小变化时重新渲染图表
  window.addEventListener('resize', () => {
    dailyChart?.resize()
  })
})

onUnmounted(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
  }
  dailyChart?.dispose()
  window.removeEventListener('resize', () => {
    dailyChart?.resize()
  })
})
</script>

<style scoped lang="scss">
.vehicle-wash-page {
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;

  h1 {
    margin: 0;
    font-size: 24px;
    color: #303133;
  }
}

.stats-row {
  margin-bottom: 20px;
}

.stat-card {
  display: flex;
  align-items: center;
  padding: 15px;
  margin-bottom: 20px;

  :deep(.el-card__body) {
    display: flex;
    align-items: center;
    padding: 0;
  }
}

.stat-icon {
  width: 50px;
  height: 50px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 15px;
  font-size: 24px;
  color: white;

  &.blue { background: linear-gradient(135deg, #409EFF, #66b1ff); }
  &.green { background: linear-gradient(135deg, #67C23A, #85ce61); }
  &.orange { background: linear-gradient(135deg, #E6A23C, #ebb563); }
  &.purple { background: linear-gradient(135deg, #909399, #a6a9ad); }
}

.stat-content {
  flex: 1;
}

.stat-value {
  font-size: 28px;
  font-weight: bold;
  color: #303133;
  line-height: 1.2;
}

.stat-label {
  font-size: 14px;
  color: #909399;
  margin-top: 5px;
}

.section-card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: bold;
}

.filter-bar {
  display: flex;
  gap: 10px;
  align-items: center;
}

.pagination-bar {
  display: flex;
  justify-content: flex-end;
  margin-top: 15px;
}

.charts-row {
  margin-top: 20px;
}

.chart-card {
  margin-bottom: 20px;
}

.chart-container {
  height: 300px;
}

.text-gray {
  color: #909399;
}

@media (max-width: 768px) {
  .filter-bar {
    flex-wrap: wrap;
  }

  .stat-value {
    font-size: 22px;
  }
}
</style>
