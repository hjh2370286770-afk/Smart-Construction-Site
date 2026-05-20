export interface Stream {
  id: string
  name: string
  url: string
  location: string
  status: 'running' | 'stopped' | 'error'
  fps: number
  resolution: string
  created_at: string
  updated_at: string
}

export interface Violation {
  id: string
  stream_id: string
  stream_name: string
  type: string
  confidence: number
  image_url: string
  timestamp: string
  location: string
}

export interface ViolationType {
  type: string
  label: string
  count: number
}

export interface StreamStats {
  stream_id: string
  stream_name: string
  violation_count: number
  fps: number
  uptime: number
}

export interface HourlyStats {
  hour: string
  count: number
}

export interface DailyReport {
  date: string
  total_violations: number
  total_streams: number
  active_streams: number
  violation_types: ViolationType[]
  hourly_stats: HourlyStats[]
  stream_stats: StreamStats[]
}

export interface SystemStatus {
  cpu_usage: number
  memory_usage: number
  disk_usage: number
  active_streams: number
  total_violations: number
  uptime: number
}

export interface DetectionConfig {
  model_path: string
  confidence_threshold: number
  iou_threshold: number
  device: string
  classes: string[]
}

export interface NotificationConfig {
  enabled: boolean
  webhooks: string[]
  emails: string[]
  min_confidence: number
  cooldown_minutes: number
}

export interface WebSocketMessage {
  type: 'violation' | 'status' | 'error'
  data: any
  timestamp: string
}
