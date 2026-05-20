<template>
  <div class="analytics-view">
    <!-- 统计卡片 -->
    <el-row :gutter="20" class="stats-row">
      <el-col :span="6">
        <el-card class="stats-card" shadow="hover">
          <div class="stats-content">
            <div class="stats-icon primary">
              <el-icon><Warning /></el-icon>
            </div>
            <div class="stats-info">
              <div class="stats-value">{{ totalViolations }}</div>
              <div class="stats-label">总违规数</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stats-card" shadow="hover">
          <div class="stats-content">
            <div class="stats-icon success">
              <el-icon><TrendCharts /></el-icon>
            </div>
            <div class="stats-info">
              <div class="stats-value">{{ todayViolations }}</div>
              <div class="stats-label">今日违规</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stats-card" shadow="hover">
          <div class="stats-content">
            <div class="stats-icon warning">
              <el-icon><VideoCamera /></el-icon>
            </div>
            <div class="stats-info">
              <div class="stats-value">{{ activeStreams }}</div>
              <div class="stats-label">活跃视频流</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stats-card" shadow="hover">
          <div class="stats-content">
            <div class="stats-icon danger">
              <el-icon><FirstAidKit /></el-icon>
            </div>
            <div class="stats-info">
              <div class="stats-value">{{ criticalViolations }}</div>
              <div class="stats-label">严重违规</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 图表区域 -->
    <el-row :gutter="20" class="charts-row">
      <el-col :span="12">
        <el-card class="chart-card" shadow="never">
          <template #header>
            <span>违规趋势 (近7天)</span>
          </template>
          <div ref="trendChart" class="chart-container"></div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card class="chart-card" shadow="never">
          <template #header>
            <span>违规类型分布</span>
          </template>
          <div ref="typeChart" class="chart-container"></div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" class="charts-row">
      <el-col :span="12">
        <el-card class="chart-card" shadow="never">
          <template #header>
            <span>各视频流违规对比</span>
          </template>
          <div ref="streamChart" class="chart-container"></div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card class="chart-card" shadow="never">
          <template #header>
            <span>24小时违规热力图</span>
          </template>
          <div ref="heatmapChart" class="chart-container"></div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useViolationsStore } from '@/stores/violations'
import { useStreamsStore } from '@/stores/streams'
import * as echarts from 'echarts'
import dayjs from 'dayjs'

const violationsStore = useViolationsStore()
const streamsStore = useStreamsStore()

const trendChart = ref<HTMLDivElement>()
const typeChart = ref<HTMLDivElement>()
const streamChart = ref<HTMLDivElement>()
const heatmapChart = ref<HTMLDivElement>()

// 统计数据
const totalViolations = computed(() => violationsStore.total)
const todayViolations = computed(() => violationsStore.todayViolations.length)
const activeStreams = computed(() => streamsStore.runningStreams.length)
const criticalViolations = computed(() => 
  violationsStore.violations.filter(v => v.severity === 'critical').length
)

// 按类型统计（使用组合类型）
const violationsByType = computed(() => {
  const counts: Record<string, number> = {}
  violationsStore.violations.forEach(v => {
    counts[v.type] = (counts[v.type] || 0) + 1
  })
  return counts
})

// 按视频流统计
const violationsByStream = computed(() => {
  const counts: Record<string, number> = {}
  violationsStore.violations.forEach(v => {
    counts[v.stream_id] = (counts[v.stream_id] || 0) + 1
  })
  return counts
})

// 按日期统计（近7天）
const violationsByDate = computed(() => {
  const counts: Record<string, number> = {}
  const today = dayjs()
  
  // 初始化近7天
  for (let i = 6; i >= 0; i--) {
    const date = today.subtract(i, 'day').format('YYYY-MM-DD')
    counts[date] = 0
  }
  
  // 统计违规
  violationsStore.violations.forEach(v => {
    const date = v.timestamp.substring(0, 10)
    if (counts.hasOwnProperty(date)) {
      counts[date]++
    }
  })
  
  return counts
})

// 按小时统计（用于热力图）
const violationsByHour = computed(() => {
  const counts: Record<string, Record<number, number>> = {}
  const today = dayjs()
  
  // 初始化近7天，每天24小时
  for (let i = 6; i >= 0; i--) {
    const date = today.subtract(i, 'day').format('YYYY-MM-DD')
    counts[date] = {}
    for (let h = 0; h < 24; h++) {
      counts[date][h] = 0
    }
  }
  
  // 统计违规
  violationsStore.violations.forEach(v => {
    const date = v.timestamp.substring(0, 10)
    const hour = parseInt(v.timestamp.substring(11, 13))
    if (counts[date] && counts[date][hour] !== undefined) {
      counts[date][hour]++
    }
  })
  
  return counts
})

const initTrendChart = () => {
  if (!trendChart.value) return
  const chart = echarts.init(trendChart.value)
  
  const data = violationsByDate.value
  const dates = Object.keys(data)
  const values = Object.values(data)
  
  const option = {
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: dates.map(d => dayjs(d).format('MM-DD'))
    },
    yAxis: { type: 'value' },
    series: [{
      data: values,
      type: 'line',
      smooth: true,
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(64, 158, 255, 0.3)' },
          { offset: 1, color: 'rgba(64, 158, 255, 0.05)' }
        ])
      }
    }]
  }
  chart.setOption(option)
}

const initTypeChart = () => {
  if (!typeChart.value) return
  const chart = echarts.init(typeChart.value)
  
  const data = violationsByType.value
  const chartData = Object.entries(data)
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 8) // 只显示前8种类型
  
  const option = {
    tooltip: { trigger: 'item' },
    legend: { 
      bottom: '5%',
      type: 'scroll'
    },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      avoidLabelOverlap: false,
      itemStyle: {
        borderRadius: 10,
        borderColor: '#fff',
        borderWidth: 2
      },
      label: { show: false },
      emphasis: {
        label: {
          show: true,
          fontSize: 14,
          fontWeight: 'bold'
        }
      },
      data: chartData
    }]
  }
  chart.setOption(option)
}

const initStreamChart = () => {
  if (!streamChart.value) return
  const chart = echarts.init(streamChart.value)
  
  const data = violationsByStream.value
  const sortedData = Object.entries(data)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10) // 只显示前10个视频流
  
  const option = {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { type: 'value' },
    yAxis: {
      type: 'category',
      data: sortedData.map(([name]) => name).reverse()
    },
    series: [{
      type: 'bar',
      data: sortedData.map(([, count]) => count).reverse(),
      itemStyle: { color: '#67c23a' }
    }]
  }
  chart.setOption(option)
}

const initHeatmapChart = () => {
  if (!heatmapChart.value) return
  const chart = echarts.init(heatmapChart.value)
  
  const data = violationsByHour.value
  const hours = Array.from({ length: 24 }, (_, i) => `${i}:00`)
  const days = Object.keys(data).sort()
  
  // 构建热力图数据
  const heatmapData: [number, number, number][] = []
  days.forEach((date, dayIndex) => {
    for (let hour = 0; hour < 24; hour++) {
      heatmapData.push([hour, dayIndex, data[date][hour] || 0])
    }
  })
  
  const option = {
    tooltip: { 
      position: 'top',
      formatter: (params: any) => {
        const day = days[params.value[1]]
        const hour = params.value[0]
        const count = params.value[2]
        return `${day} ${hour}:00<br/>违规数: ${count}`
      }
    },
    grid: { height: '50%', top: '10%' },
    xAxis: { 
      type: 'category', 
      data: hours,
      splitArea: { show: true }
    },
    yAxis: { 
      type: 'category', 
      data: days.map(d => dayjs(d).format('MM-DD')),
      splitArea: { show: true }
    },
    visualMap: {
      min: 0,
      max: Math.max(...heatmapData.map(d => d[2]), 10),
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: '15%',
      inRange: { color: ['#f0f9ff', '#1890ff'] }
    },
    series: [{
      type: 'heatmap',
      data: heatmapData,
      label: { show: false },
      emphasis: {
        itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0, 0, 0, 0.5)' }
      }
    }]
  }
  chart.setOption(option)
}

onMounted(async () => {
  // 获取所有违规记录（使用较大的page_size获取全部数据）
  await violationsStore.fetchViolations({ page_size: 10000 })
  await streamsStore.fetchStreams()
  

  
  // 初始化图表
  initTrendChart()
  initTypeChart()
  initStreamChart()
  initHeatmapChart()
  
  window.addEventListener('resize', () => {
    echarts.getInstanceByDom(trendChart.value!)?.resize()
    echarts.getInstanceByDom(typeChart.value!)?.resize()
    echarts.getInstanceByDom(streamChart.value!)?.resize()
    echarts.getInstanceByDom(heatmapChart.value!)?.resize()
  })
})
</script>

<style scoped lang="scss">
.analytics-view {
  .stats-row {
    margin-bottom: 20px;

    .stats-card {
      .stats-content {
        display: flex;
        align-items: center;
        gap: 16px;

        .stats-icon {
          width: 60px;
          height: 60px;
          border-radius: 12px;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 28px;

          &.primary {
            background: #e6f7ff;
            color: #1890ff;
          }

          &.success {
            background: #f6ffed;
            color: #52c41a;
          }

          &.warning {
            background: #fff2e8;
            color: #fa8c16;
          }

          &.danger {
            background: #fff1f0;
            color: #f5222d;
          }
        }

        .stats-info {
          .stats-value {
            font-size: 28px;
            font-weight: 600;
            color: #303133;
            line-height: 1;
          }

          .stats-label {
            font-size: 14px;
            color: #909399;
            margin-top: 8px;
          }
        }
      }
    }
  }

  .charts-row {
    margin-bottom: 20px;

    .chart-card {
      .chart-container {
        height: 300px;
      }
    }
  }
}
</style>
