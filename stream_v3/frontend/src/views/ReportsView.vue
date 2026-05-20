<template>
  <div class="reports-view">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <h3>日报系统</h3>
          <div class="header-actions">
            <el-button type="primary" @click="generateSelectedDateReport" :loading="loading">
              <el-icon><Document /></el-icon>
              生成选中日期日报
            </el-button>
            <el-button @click="generateTodayReport" :loading="loading">
              <el-icon><Calendar /></el-icon>
              生成今日日报
            </el-button>
          </div>
        </div>
      </template>

      <!-- 日期选择 -->
      <div class="date-selector">
        <el-date-picker
          v-model="selectedDate"
          type="date"
          placeholder="选择日期"
          value-format="YYYY-MM-DD"
          @change="handleDateChange"
        />
        <el-select v-model="selectedCamera" placeholder="选择视频流" clearable style="margin-left: 12px;">
          <el-option label="全部视频流" value="" />
          <el-option
            v-for="stream in streamsStore.streams"
            :key="stream.id"
            :label="stream.name"
            :value="stream.id"
          />
        </el-select>
      </div>

      <!-- 日报内容 -->
      <div v-if="currentReport" class="report-content">
        <div class="report-header">
          <h2>{{ currentReport.title }}</h2>
          <p class="report-date">生成时间: {{ currentReport.generatedAt }}</p>
        </div>

        <!-- 统计概览 -->
        <el-row :gutter="20" class="stats-overview">
          <el-col :span="6">
            <div class="stat-box">
              <div class="stat-number">{{ currentReport.totalViolations }}</div>
              <div class="stat-label">总违规数</div>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="stat-box">
              <div class="stat-number">{{ currentReport.peakHour || '-' }}</div>
              <div class="stat-label">高峰时段</div>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="stat-box">
              <div class="stat-number">{{ currentReport.activeStreams }}</div>
              <div class="stat-label">活跃视频流</div>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="stat-box">
              <div class="stat-number">{{ currentReport.detectionCount || currentReport.totalViolations }}</div>
              <div class="stat-label">检测次数</div>
            </div>
          </el-col>
        </el-row>

        <!-- 图表 -->
        <el-row :gutter="20" class="chart-row">
          <el-col :span="12">
            <div ref="hourlyChart" class="chart-container"></div>
          </el-col>
          <el-col :span="12">
            <div ref="typeChart" class="chart-container"></div>
          </el-col>
        </el-row>

        <!-- 操作按钮 -->
        <div class="report-actions">
          <el-button type="primary" @click="downloadPDF">
            <el-icon><Download /></el-icon>
            下载PDF
          </el-button>
          <el-button @click="printReport">
            <el-icon><Printer /></el-icon>
            打印
          </el-button>
        </div>
      </div>

      <el-empty v-else description="请选择日期查看日报" />
    </el-card>

    <!-- 历史日报列表 -->
    <el-card class="history-card" shadow="never">
      <template #header>
        <span>历史日报</span>
      </template>
      <el-table :data="historyReports" style="width: 100%" v-loading="historyLoading">
        <el-table-column prop="date" label="日期" width="120" />
        <el-table-column prop="total_violations" label="违规数" width="100" />
        <el-table-column prop="created_at" label="生成时间">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150">
          <template #default="{ row }">
            <el-button link type="primary" @click="viewReport(row)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { useStreamsStore } from '@/stores/streams'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import dayjs from 'dayjs'
import { reportsApi } from '@/api'

const streamsStore = useStreamsStore()

const selectedDate = ref(dayjs().format('YYYY-MM-DD'))
const selectedCamera = ref('')
const currentReport = ref<any>(null)
const historyReports = ref<any[]>([])
const loading = ref(false)
const historyLoading = ref(false)

const hourlyChart = ref<HTMLDivElement>()
const typeChart = ref<HTMLDivElement>()

// 格式化时间
const formatTime = (timestamp: string) => {
  if (!timestamp) return '-'
  return dayjs(timestamp).format('YYYY-MM-DD HH:mm:ss')
}

// 加载日报数据
const handleDateChange = async () => {
  if (!selectedDate.value) return
  
  loading.value = true
  try {
    const report = await reportsApi.getDaily(selectedDate.value)
    
    // 后端已经解析了JSON字段，直接使用
    const violationTypes = report.violation_types || []
    const hourlyStats = report.hourly_stats || []
    const streamStats = report.stream_stats || []
    
    // 计算高峰时段
    let peakHour = '-'
    let maxCount = 0
    hourlyStats.forEach((item: any) => {
      if (item.count > maxCount) {
        maxCount = item.count
        peakHour = item.hour
      }
    })
    
    // 构建24小时数据数组（只显示有数据的小时）
    const hourlyData = new Array(24).fill(0)
    hourlyStats.forEach((item: any) => {
      const hour = parseInt(item.hour)
      if (!isNaN(hour) && hour >= 0 && hour < 24) {
        hourlyData[hour] = item.count
      }
    })
    
    currentReport.value = {
      title: `${report.date} 监控日报`,
      generatedAt: formatTime(report.created_at),
      totalViolations: report.total_violations,
      peakHour: peakHour !== '-' ? `${peakHour}-${String(parseInt(peakHour) + 1).padStart(2, '0')}:00` : '-',
      activeStreams: report.active_streams,
      detectionCount: report.total_violations,
      hourlyData: hourlyData,
      typeData: violationTypes.map((item: any) => ({
        name: item.label || item.type,
        value: item.count
      }))
    }
    
    // 等待DOM更新后初始化图表
    nextTick(() => {
      initCharts()
    })
  } catch (error) {
    console.error('加载日报失败:', error)
    ElMessage.error('加载日报失败')
    currentReport.value = null
  } finally {
    loading.value = false
  }
}

// 生成选中日期日报
const generateSelectedDateReport = async () => {
  if (!selectedDate.value) {
    ElMessage.warning('请先选择日期')
    return
  }
  
  loading.value = true
  try {
    await reportsApi.generate(selectedDate.value)
    ElMessage.success(`${selectedDate.value} 日报生成成功`)
    await handleDateChange()
    await loadHistoryReports()
  } catch (error) {
    console.error('生成日报失败:', error)
    ElMessage.error('生成日报失败')
  } finally {
    loading.value = false
  }
}

// 生成今日日报
const generateTodayReport = async () => {
  selectedDate.value = dayjs().format('YYYY-MM-DD')
  
  loading.value = true
  try {
    await reportsApi.generate(selectedDate.value)
    ElMessage.success('今日日报生成成功')
    await handleDateChange()
    await loadHistoryReports()
  } catch (error) {
    console.error('生成日报失败:', error)
    ElMessage.error('生成日报失败')
  } finally {
    loading.value = false
  }
}

// 加载历史日报列表
const loadHistoryReports = async () => {
  historyLoading.value = true
  try {
    const result = await reportsApi.getHistory({ page: 1, page_size: 20 })
    historyReports.value = result.items || []
  } catch (error) {
    console.error('加载历史日报失败:', error)
  } finally {
    historyLoading.value = false
  }
}

// 初始化图表
const initCharts = () => {
  if (!currentReport.value) return
  
  // 24小时趋势图
  if (hourlyChart.value) {
    const chart = echarts.init(hourlyChart.value)
    chart.setOption({
      title: { text: '24小时违规分布', left: 'center' },
      tooltip: { trigger: 'axis' },
      xAxis: {
        type: 'category',
        data: Array.from({ length: 24 }, (_, i) => `${i}:00`)
      },
      yAxis: { type: 'value' },
      series: [{
        data: currentReport.value.hourlyData,
        type: 'bar',
        itemStyle: { color: '#409EFF' }
      }]
    })
  }
  
  // 违规类型饼图
  if (typeChart.value) {
    const chart = echarts.init(typeChart.value)
    chart.setOption({
      title: { text: '违规类型分布', left: 'center' },
      tooltip: { trigger: 'item' },
      series: [{
        type: 'pie',
        radius: '60%',
        data: currentReport.value.typeData
      }]
    })
  }
}

const downloadPDF = () => {
  ElMessage.success('PDF下载中...')
}

const printReport = () => {
  window.print()
}

const viewReport = (row: any) => {
  selectedDate.value = row.date
  handleDateChange()
}

onMounted(() => {
  streamsStore.fetchStreams()
  handleDateChange()
  loadHistoryReports()
})
</script>

<style scoped lang="scss">
.reports-view {
  .card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;

    h3 {
      margin: 0;
      font-size: 18px;
      font-weight: 600;
    }

    .header-actions {
      display: flex;
      gap: 12px;
    }
  }

  .date-selector {
    margin-bottom: 20px;
    padding: 16px;
    background: #f5f7fa;
    border-radius: 8px;
  }

  .report-content {
    .report-header {
      text-align: center;
      margin-bottom: 30px;

      h2 {
        margin: 0 0 8px 0;
        font-size: 24px;
        color: #303133;
      }

      .report-date {
        color: #909399;
        font-size: 14px;
      }
    }

    .stats-overview {
      margin-bottom: 30px;

      .stat-box {
        text-align: center;
        padding: 24px;
        background: #f5f7fa;
        border-radius: 8px;

        .stat-number {
          font-size: 32px;
          font-weight: 600;
          color: #409EFF;
          line-height: 1;
        }

        .stat-label {
          font-size: 14px;
          color: #606266;
          margin-top: 8px;
        }
      }
    }

    .chart-row {
      margin-bottom: 30px;

      .chart-container {
        height: 300px;
      }
    }

    .report-actions {
      display: flex;
      justify-content: center;
      gap: 16px;
      padding-top: 20px;
      border-top: 1px solid #ebeef5;
    }
  }

  .history-card {
    margin-top: 20px;
  }
}
</style>
