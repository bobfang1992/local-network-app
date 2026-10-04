import { Fragment, useState, useEffect, useRef } from 'react'
import './App.css'

const SETTINGS_STORAGE_KEY = 'local-network-ui-settings'

const loadSettings = () => {
  try {
    const raw = localStorage.getItem(SETTINGS_STORAGE_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

const saveSettings = (settings) => {
  try {
    localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings))
  } catch {
    // Ignore storage failures (private mode, quota, etc.)
  }
}

/**
 * 测速历史折线图。内联 SVG,不引图表库 —— 为一条折线装 Chart.js 不值,
 * 而且那种风格和这个站不搭。
 *
 * ⚠️ **X 轴按真实时间,不按第几个点。** 等距排点会把「6 小时一次」和
 *    「手动连测两次」画成一样宽,于是**图上看不出中间断过** ——
 *    而「断过」正是看这张图时最该发现的事。
 *
 * ⚠️ **失败的那几次画成底部的红点。** 它们在数据里(ok=0),
 *    跳过不画的话,断网期会变成一段平滑的连线,读起来像一切正常。
 */
function SpeedChart({ rows }) {
  const W = 300, H = 110, PAD = { l: 34, r: 8, t: 8, b: 16 }
  const good = (rows || []).filter(r => r.ok && r.download_mbps != null)
  if (good.length < 2) {
    return (
      <div style={{ fontSize: '0.75rem', color: '#888', padding: '0.4rem 0' }}>
        {good.length === 0 ? '还没有数据' : '只有 1 个点 —— 再测一次就能画线了'}
      </div>
    )
  }
  const t = r => new Date(r.run_at).getTime()
  const pts = [...good].sort((a, b) => t(a) - t(b))
  const t0 = t(pts[0]), t1 = t(pts[pts.length - 1])
  const span = Math.max(1, t1 - t0)
  // 纵轴取整到 100 的倍数,刻度别出现 845/423 这种怪数
  const maxY = Math.max(100, Math.ceil(Math.max(...pts.map(r => Math.max(r.download_mbps, r.upload_mbps || 0))) * 1.1 / 100) * 100)
  const x = r => PAD.l + ((t(r) - t0) / span) * (W - PAD.l - PAD.r)
  const y = v => H - PAD.b - (v / maxY) * (H - PAD.t - PAD.b)
  const line = key => pts.map(r => `${x(r).toFixed(1)},${y(r[key] || 0).toFixed(1)}`).join(' ')
  const fails = (rows || []).filter(r => !r.ok && t(r) >= t0 && t(r) <= t1)
  const fmt = ms => {
    const d = new Date(ms)
    return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  }
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 'auto' }} role="img"
           aria-label="测速历史">
        {[0, maxY / 2, maxY].map((v, i) => (
          <g key={i}>
            <line x1={PAD.l} y1={y(v)} x2={W - PAD.r} y2={y(v)} stroke="#e8e8e8" strokeWidth="1" />
            <text x={PAD.l - 4} y={y(v) + 3} textAnchor="end" fontSize="7" fill="#888">{Math.round(v)}</text>
          </g>
        ))}
        <polyline points={line('download_mbps')} fill="none" stroke="#111" strokeWidth="1.6" />
        <polyline points={line('upload_mbps')} fill="none" stroke="#999" strokeWidth="1.6"
                  strokeDasharray="3 2" />
        {pts.map((r, i) => <circle key={i} cx={x(r)} cy={y(r.download_mbps)} r="1.8" fill="#111" />)}
        {/* 失败的测速:底部红点。不画的话断网期会变成一段平滑连线 */}
        {fails.map((r, i) => <circle key={'f' + i} cx={x(r)} cy={H - PAD.b} r="2.2" fill="#c0392b" />)}
        <text x={PAD.l} y={H - 4} fontSize="7" fill="#888">{fmt(t0)}</text>
        <text x={W - PAD.r} y={H - 4} fontSize="7" fill="#888" textAnchor="end">{fmt(t1)}</text>
      </svg>
      <div style={{ fontSize: '0.68rem', color: '#666', display: 'flex', gap: '0.75rem' }}>
        <span><span style={{ color: "#111" }}>━</span> 下行</span>
        <span><span style={{ color: "#999" }}>┅</span> 上行</span>
        {fails.length > 0 && <span><span style={{ color: '#c0392b' }}>●</span> 失败 {fails.length}</span>}
        <span style={{ marginLeft: 'auto' }}>Mbps · {pts.length} 次</span>
      </div>
    </div>
  )
}

function App() {
  const initialSettings = typeof window !== 'undefined' ? loadSettings() : {}
  const [devices, setDevices] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [lastUpdate, setLastUpdate] = useState(null)
  const [connected, setConnected] = useState(false)
  const [speedtest, setSpeedtest] = useState(null)
  const [speedRunning, setSpeedRunning] = useState(false)
  const [nextScan, setNextScan] = useState(null)
  const [, setScanInterval] = useState(30) // 改版后不再画进度条,保留 setter 以免改 WS 处理
  const [countdown, setCountdown] = useState(null)
  const [scanLog, setScanLog] = useState([])
  const [activeTab, setActiveTab] = useState(initialSettings.activeTab || 'devices')
  const [dbStats, setDbStats] = useState(null)
  const [catLog, setCatLog] = useState(null)
  const [editingNotes, setEditingNotes] = useState(null) // IP of device being edited
  const [sortColumn, setSortColumn] = useState(initialSettings.sortColumn || 'ip')
  const [sortDirection, setSortDirection] = useState(initialSettings.sortDirection || 'asc')
  const [expandedDevice, setExpandedDevice] = useState(null) // IP of expanded device
  const [portScanResults, setPortScanResults] = useState({}) // Map of IP -> port scan results
  const [scanningPorts, setScanningPorts] = useState({}) // Map of IP -> scanning status
  const [portScanTimeout, setPortScanTimeout] = useState(initialSettings.portScanTimeout ?? 2.5)
  const [portScanWorkers, setPortScanWorkers] = useState(initialSettings.portScanWorkers ?? 15)
  const [portScanRetries, setPortScanRetries] = useState(initialSettings.portScanRetries ?? 2)
  const [serviceScanEnabled, setServiceScanEnabled] = useState(initialSettings.serviceScanEnabled ?? false)
  const [startupFullScanEnabled, setStartupFullScanEnabled] = useState(initialSettings.startupFullScanEnabled ?? false)
  const [startupFullScanBudgetSec, setStartupFullScanBudgetSec] = useState(initialSettings.startupFullScanBudgetSec ?? 120)
  const [toast, setToast] = useState(null)
  const [fullScanProgress, setFullScanProgress] = useState({ active: false, completed: 0, total: 0, label: '' })
  const [scanningOS, setScanningOS] = useState({})
  const [scanningSSDP, setScanningSSDP] = useState({})
  const [filter, setFilter] = useState('all')
  const [query, setQuery] = useState('')
  const [panel, setPanel] = useState(null) // null | 'speed' | 'settings'
  const wsRef = useRef(null)
  const reconnectTimeoutRef = useRef(null)
  const countdownIntervalRef = useRef(null)
  const toastTimeoutRef = useRef(null)
  const startupScanRunRef = useRef(false)

  const connectWebSocket = () => {
    try {
      const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`)
      wsRef.current = ws

      ws.onopen = () => {
        console.log('WebSocket connected')
        setConnected(true)
        setError(null)
        setLoading(false)
      }

      ws.onmessage = (event) => {
        const message = JSON.parse(event.data)
        console.log('WebSocket message:', message)

        // Handle scan progress messages
        if (message.type === 'scan_start' || message.type === 'scan_progress' || message.type === 'scan_error') {
          const logEntry = {
            timestamp: new Date().toLocaleTimeString(),
            message: message.message,
            type: message.type
          }
          setScanLog(prev => [logEntry, ...prev].slice(0, 10)) // Keep last 10 messages
        }

        if (message.type === 'initial_state' || message.type === 'scan_update') {
          setDevices(message.devices || [])

          if (message.timestamp) {
            const date = new Date(message.timestamp)
            setLastUpdate(date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false }))
          }

          if (message.next_scan) {
            setNextScan(new Date(message.next_scan))
          }

          if (message.scan_interval) {
            setScanInterval(message.scan_interval)
          }

          setLoading(false)
        }
      }

      ws.onerror = (event) => {
        console.error('WebSocket error:', event)
        setError('Connection error. Make sure the backend is running with sudo.')
      }

      ws.onclose = () => {
        console.log('WebSocket disconnected')
        setConnected(false)
        setLoading(true)

        // Attempt to reconnect after 3 seconds
        reconnectTimeoutRef.current = setTimeout(() => {
          console.log('Attempting to reconnect...')
          connectWebSocket()
        }, 3000)
      }
    } catch (err) {
      console.error('Failed to connect WebSocket:', err)
      setError('Unable to connect to backend')
    }
  }

  const scanNow = () => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      setLoading(true)
      wsRef.current.send(JSON.stringify({ type: 'scan_now' }))
    }
  }

  const showToast = (message, type = 'info') => {
    setToast({ message, type })
    if (toastTimeoutRef.current) {
      clearTimeout(toastTimeoutRef.current)
    }
    toastTimeoutRef.current = setTimeout(() => {
      setToast(null)
    }, 3500)
  }

  useEffect(() => {
    fetchSpeedtest()
    // 顶部「见过」要数据库里的设备总数;不在调试页时也拉一次,之后每 5 分钟刷新
    fetchDbStats()
    const t = setInterval(fetchDbStats, 5 * 60 * 1000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    saveSettings({
      activeTab,
      sortColumn,
      sortDirection,
      portScanTimeout,
      portScanWorkers,
      portScanRetries,
      serviceScanEnabled,
      startupFullScanEnabled,
      startupFullScanBudgetSec
    })
  }, [
    activeTab,
    sortColumn,
    sortDirection,
    portScanTimeout,
    portScanWorkers,
    portScanRetries,
    serviceScanEnabled,
    startupFullScanEnabled,
    startupFullScanBudgetSec
  ])

  const fetchSpeedtest = async () => {
    try {
      const r = await fetch('/api/speedtest?limit=20')
      const d = await r.json()
      if (d.success) setSpeedtest(d)
    } catch (e) {
      // 取不到测速不该影响别的 —— 这一格留空就好
    }
  }

  const runSpeedtestNow = async () => {
    setSpeedRunning(true)
    try {
      await fetch('/api/speedtest/run', { method: 'POST' })
      await fetchSpeedtest()
    } catch (e) {
      // 同上
    } finally {
      setSpeedRunning(false)
    }
  }

  const fetchDbStats = async () => {
    try {
      const response = await fetch('/api/database/stats')
      const data = await response.json()
      setDbStats(data)
    } catch (err) {
      console.error('Failed to fetch database stats:', err)
    }
  }

  const fetchCatLog = async () => {
    try {
      const response = await fetch('/api/categorization/log?limit=50')
      const data = await response.json()
      setCatLog(data)
    } catch (err) {
      console.error('Failed to fetch categorization log:', err)
    }
  }

  const updateNotes = async (ip, notes) => {
    try {
      const response = await fetch(`/api/devices/${ip}/notes`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ notes })
      })
      const data = await response.json()
      if (data.success) {
        // Update local state
        setDevices(devices.map(d =>
          d.ip === ip ? { ...d, notes } : d
        ))
        setEditingNotes(null) // Exit edit mode
      }
    } catch (err) {
      console.error('Failed to update notes:', err)
    }
  }

  const handleNotesKeyPress = (e, ip) => {
    if (e.key === 'Enter') {
      // Get the current value from the input field
      updateNotes(ip, e.target.value)
    } else if (e.key === 'Escape') {
      setEditingNotes(null)
    }
  }

  const scanPorts = async (ip, options = {}) => {
    const { serviceScanOverride } = options
    try {
      // Set scanning state
      setScanningPorts(prev => ({ ...prev, [ip]: true }))

      const serviceScan = serviceScanOverride !== undefined ? serviceScanOverride : serviceScanEnabled
      const response = await fetch(`/api/devices/${ip}/scan-ports?timeout=${portScanTimeout}&max_workers=${portScanWorkers}&retries=${portScanRetries}&service_scan=${serviceScan}`, {
        method: 'POST'
      })
      const data = await response.json()

      if (data.success) {
        // Store results
        setPortScanResults(prev => ({
          ...prev,
          [ip]: {
            ports: data.ports,
            scan_time: new Date().toISOString(),
            pihole: data.pihole || null
          }
        }))
        // Expand the device to show results
        setExpandedDevice(ip)
        if (data.service_scan_error) {
          showToast(data.service_scan_error, 'error')
        }
      } else {
        showToast(data.message || `Port scan failed for ${ip}`, 'error')
      }
    } catch (err) {
      console.error('Failed to scan ports:', err)
      showToast(`Port scan failed for ${ip}`, 'error')
    } finally {
      setScanningPorts(prev => ({ ...prev, [ip]: false }))
    }
  }

  const scanOS = async (ip) => {
    try {
      setScanningOS(prev => ({ ...prev, [ip]: true }))
      const response = await fetch(`/api/devices/${ip}/scan-os`, {
        method: 'POST'
      })
      const data = await response.json()

      if (data.success) {
        setDevices(prev =>
          prev.map(d => d.ip === ip ? {
            ...d,
            os_guess: data.os_guess || '',
            os_accuracy: data.os_accuracy,
            os_scanned_at: data.os_scanned_at,
            os_last_error: ''
          } : d)
        )
      } else {
        const errorMessage = data.message || `OS scan failed for ${ip}`
        setDevices(prev =>
          prev.map(d => d.ip === ip ? { ...d, os_last_error: errorMessage } : d)
        )
        showToast(errorMessage, 'error')
      }
    } catch (err) {
      console.error('OS scan failed:', err)
      showToast(`OS scan failed for ${ip}`, 'error')
    } finally {
      setScanningOS(prev => ({ ...prev, [ip]: false }))
    }
  }

  const scanSSDP = async (ip) => {
    try {
      setScanningSSDP(prev => ({ ...prev, [ip]: true }))
      const response = await fetch(`/api/devices/${ip}/discover-ssdp`, {
        method: 'POST'
      })
      const data = await response.json()

      if (data.success && data.ssdp) {
        setDevices(prev =>
          prev.map(d => d.ip === ip ? {
            ...d,
            ssdp_server: data.ssdp.server || '',
            ssdp_location: data.ssdp.location || '',
            ssdp_st: data.ssdp.st || '',
            ssdp_usn: data.ssdp.usn || '',
            ssdp_scanned_at: new Date().toISOString()
          } : d)
        )
      } else {
        showToast(data.message || `SSDP discovery failed for ${ip}`, 'error')
      }
    } catch (err) {
      console.error('SSDP discovery failed:', err)
      showToast(`SSDP discovery failed for ${ip}`, 'error')
    } finally {
      setScanningSSDP(prev => ({ ...prev, [ip]: false }))
    }
  }

  const scanAllDevices = async () => {
    const onlineDevices = devices.filter(d => d.status === 'online')

    if (onlineDevices.length === 0) {
      showToast('No online devices to scan', 'error')
      return
    }

    if (!confirm(`Scan ports on ${onlineDevices.length} online devices? This may take a few minutes.`)) {
      return
    }

    // Scan devices sequentially to avoid overwhelming the network
    for (const device of onlineDevices) {
      await scanPorts(device.ip)
      // Small delay between devices
      await new Promise(resolve => setTimeout(resolve, 500))
    }
  }

  const runStartupFullScan = async (onlineDevices) => {
    if (!onlineDevices.length) {
      showToast('No online devices to scan', 'error')
      return
    }

    const totalSteps = onlineDevices.length * 3
    setFullScanProgress({ active: true, completed: 0, total: totalSteps, label: 'Running full scan' })

    const budgetMs = Math.max(30, startupFullScanBudgetSec) * 1000
    const startTime = Date.now()

    let completed = 0
    for (const device of onlineDevices) {
      if (Date.now() - startTime > budgetMs) {
        showToast('Full scan exceeded time budget', 'error')
        break
      }

      await scanPorts(device.ip, { serviceScanOverride: true })
      completed += 1
      setFullScanProgress(prev => ({ ...prev, completed }))

      if (Date.now() - startTime > budgetMs) {
        showToast('Full scan exceeded time budget', 'error')
        break
      }

      await scanOS(device.ip)
      completed += 1
      setFullScanProgress(prev => ({ ...prev, completed }))

      if (Date.now() - startTime > budgetMs) {
        showToast('Full scan exceeded time budget', 'error')
        break
      }

      await scanSSDP(device.ip)
      completed += 1
      setFullScanProgress(prev => ({ ...prev, completed }))

      await new Promise(resolve => setTimeout(resolve, 250))
    }

    setFullScanProgress(prev => ({ ...prev, active: false, label: '' }))
  }

  const toggleExpandDevice = (ip) => {
    if (expandedDevice === ip) {
      setExpandedDevice(null)
    } else {
      setExpandedDevice(ip)
    }
  }

  const handleSort = (column) => {
    if (sortColumn === column) {
      // Toggle direction if same column
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc')
    } else {
      // New column, default to ascending
      setSortColumn(column)
      setSortDirection('asc')
    }
  }

  const getSortedDevices = () => {
    const sorted = [...devices].sort((a, b) => {
      let aVal = a[sortColumn]
      let bVal = b[sortColumn]

      if (aVal === undefined || aVal === null) aVal = ''
      if (bVal === undefined || bVal === null) bVal = ''

      // Handle special cases
      if (sortColumn === 'ip') {
        // Sort IP addresses numerically
        const aNum = aVal.split('.').map(num => parseInt(num).toString().padStart(3, '0')).join('.')
        const bNum = bVal.split('.').map(num => parseInt(num).toString().padStart(3, '0')).join('.')
        aVal = aNum
        bVal = bNum
      }

      // String comparison
      if (typeof aVal === 'string') {
        aVal = aVal.toLowerCase()
        bVal = (bVal || '').toLowerCase()
      }

      if (aVal < bVal) return sortDirection === 'asc' ? -1 : 1
      if (aVal > bVal) return sortDirection === 'asc' ? 1 : -1
      return 0
    })

    return sorted
  }

  const generateCSV = () => {
    if (!dbStats || !dbStats.devices) return ''

    const headers = ['IP', 'Hostname', 'Vendor', 'Total Scans', 'Scans Online', 'Appearance Rate (%)', 'Category', 'Notes']
    const rows = dbStats.devices.map(d => [
      d.ip,
      d.hostname,
      d.vendor || '',
      d.total_scans,
      d.scans_seen_online,
      d.appearance_rate,
      d.category,
      d.notes || ''
    ])

    const csv = [
      headers.join(','),
      ...rows.map(row => row.map(cell => `"${cell}"`).join(','))
    ].join('\n')

    return csv
  }

  const copyCSV = () => {
    const csv = generateCSV()
    navigator.clipboard.writeText(csv)
    showToast('CSV copied to clipboard', 'success')
  }

  const downloadCSV = () => {
    const csv = generateCSV()
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `network-devices-${new Date().toISOString()}.csv`
    a.click()
    URL.revokeObjectURL(url)
    showToast('CSV download started', 'success')
  }

  useEffect(() => {
    if (!startupFullScanEnabled || startupScanRunRef.current) {
      return
    }

    if (!connected || devices.length === 0 || loading) {
      return
    }

    const onlineDevices = devices.filter(d => d.status === 'online')
    startupScanRunRef.current = true
    runStartupFullScan(onlineDevices)
  }, [startupFullScanEnabled, connected, devices, loading])

  // Countdown timer effect
  useEffect(() => {
    if (nextScan) {
      // Clear existing interval
      if (countdownIntervalRef.current) {
        clearInterval(countdownIntervalRef.current)
      }

      // Update countdown every second
      countdownIntervalRef.current = setInterval(() => {
        const now = new Date()
        const diff = nextScan - now

        if (diff <= 0) {
          setCountdown(0)
        } else {
          setCountdown(Math.ceil(diff / 1000))
        }
      }, 1000)

      // Initial update
      const now = new Date()
      const diff = nextScan - now
      setCountdown(Math.ceil(diff / 1000))

      return () => {
        if (countdownIntervalRef.current) {
          clearInterval(countdownIntervalRef.current)
        }
      }
    }
  }, [nextScan])

  useEffect(() => {
    connectWebSocket()

    return () => {
      // Cleanup on unmount
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
      if (countdownIntervalRef.current) {
        clearInterval(countdownIntervalRef.current)
      }
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [])

  // Fetch database stats when debug tab is active
  useEffect(() => {
    if (activeTab === 'debug') {
      fetchDbStats()
      fetchCatLog()
      const interval = setInterval(() => {
        fetchDbStats()
        fetchCatLog()
      }, 5000) // Refresh every 5 seconds
      return () => clearInterval(interval)
    }
  }, [activeTab])

  // ---------- 值班表(2026-10-03 改版,oil-ui 方向 01)----------
  // 原来的右侧 STATUS 栏在 ~1300px 以下会压在表格上;现在全局状态压成顶部一行,
  // 测速图和扫描设置收进可展开的面板,单台设备的操作收进行内「⋯」。
  const isUnnamed = d => !(d.notes || '').trim() && (!d.hostname || d.hostname === 'Unknown')
  // 「要你看一眼」的设备:在线但没名字,或者刚出现(前 3 次扫描)。它们置顶,别让人往下翻才看到
  const needsAttention = d => (d.status === 'online' && isUnnamed(d)) || d.category === 'new'
  const pad = n => String(n).padStart(2, '0')
  // 全站统一一种时间格式:MM-DD HH:mm(24 小时制)
  const fmtTime = v => {
    if (!v) return '—'
    const d = new Date(v)
    return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
  }
  const ago = v => {
    if (!v) return ''
    const m = Math.round((Date.now() - new Date(v).getTime()) / 60000)
    if (m < 60) return `${Math.max(1, m)} 分钟前`
    if (m < 48 * 60) return `${Math.round(m / 60)} 小时前`
    return `${Math.round(m / 1440)} 天前`
  }
  const rateOf = d => {
    const v = d.appearance_rate
    if (v === undefined || v === null) return null
    return v > 1 ? v / 100 : v
  }
  const subnet = devices.length ? devices[0].ip.split('.').slice(0, 3).join('.') + '.0/24' : '局域网'
  const onlineCount = devices.filter(d => d.status === 'online').length
  const unnamedCount = devices.filter(d => d.status === 'online' && isUnnamed(d)).length
  const offlineCount = devices.filter(d => d.status !== 'online').length
  const okRuns = (speedtest?.history || []).filter(r => r.ok && r.download_mbps != null)
    .sort((a, b) => new Date(a.run_at) - new Date(b.run_at))
  const latest = speedtest?.latest_ok
  const prior = okRuns.slice(0, -1).map(r => r.download_mbps).sort((a, b) => a - b)
  const typical = prior.length ? prior[Math.floor(prior.length / 2)] : null
  // 「异常」= 低于平时中位数的四分之一。阈值宽一点:测速本来就抖,别天天报红
  const speedAlert = Boolean(latest && typical && latest.download_mbps < typical * 0.25)
  const fmtMbps = v => (v >= 10 ? Math.round(v) : v.toFixed(1))
  const fmtCountdown = s => {
    if (s === null || s === undefined) return '—'
    if (s >= 3600) return `${Math.floor(s / 3600)} 小时 ${Math.floor((s % 3600) / 60)} 分`
    if (s >= 60) return `${Math.floor(s / 60)} 分`
    return `${s} 秒`
  }
  const sparkline = (vals, w = 84, h = 20) => {
    if (vals.length < 2) return null
    const mx = Math.max(...vals) || 1
    const pts = vals.map((v, i) => `${(i * w / (vals.length - 1)).toFixed(1)},${(h - 2 - (v / mx) * (h - 4)).toFixed(1)}`).join(' ')
    return <svg className="spark" viewBox={`0 0 ${w} ${h}`} width={w} height={h} aria-hidden="true">
      <polyline points={pts} fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
    </svg>
  }
  const q = query.trim().toLowerCase()
  const visible = getSortedDevices()
    .filter(d => filter === 'all' || (filter === 'online' && d.status === 'online')
      || (filter === 'offline' && d.status !== 'online')
      || (filter === 'unnamed' && d.status === 'online' && isUnnamed(d)))
    .filter(d => !q || [d.ip, d.hostname, d.notes, d.mac, d.vendor].some(v => (v || '').toLowerCase().includes(q)))
  const attention = visible.filter(needsAttention)
  const rest = visible.filter(d => !needsAttention(d))
  const catTag = { new: '新', occasional: '偶尔', rare: '少见' }
  const catHint = { new: '前 3 次扫描内', occasional: '出现率 30–70%', rare: '出现率低于 30%' }
  const sortMark = col => sortColumn === col ? (sortDirection === 'asc' ? ' ↑' : ' ↓') : ''
  const Th = ({ col, children, className }) => (
    <th className={className} onClick={() => handleSort(col)} aria-sort={sortColumn === col ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'}>
      {children}{sortMark(col)}
    </th>
  )

  return (
    <div className="ledger">
      {fullScanProgress.active && (
        <div className="progress-top"><i style={{ width: fullScanProgress.total ? `${(fullScanProgress.completed / fullScanProgress.total) * 100}%` : '0%' }} /></div>
      )}
      {toast && <div className={`toast toast-${toast.type}`}>{toast.message}</div>}

      <header className="strip">
        <h1>{subnet}</h1>
        {[['online', '在线', onlineCount], ['unnamed', '未命名', unnamedCount], ['offline', '离线', offlineCount]].map(([k, label, n]) => (
          <button key={k} className={`stat link ${filter === k ? 'on' : ''} ${k === 'unnamed' && n ? 'alert' : ''}`}
                  onClick={() => setFilter(filter === k ? 'all' : k)} aria-pressed={filter === k}>
            <b>{n}</b>{label}
          </button>
        ))}
        <span className="seen" title="数据库里记录过的设备总数">共见过 {dbStats ? dbStats.total_devices : '—'} 台</span>
        <button className="stat link speed" onClick={() => setPanel(panel === 'speed' ? null : 'speed')}
                aria-expanded={panel === 'speed'} title="点开看测速历史">
          {latest ? <><b className={speedAlert ? 'alert' : ''}>↓{fmtMbps(latest.download_mbps)}</b>Mbps ↑{fmtMbps(latest.upload_mbps)}{typical ? ` · 平时 ${Math.round(typical)}` : ''}</> : '还没测过速'}
          {sparkline(okRuns.map(r => r.download_mbps))}
        </button>
        <span className="grow" />
        <span className={`conn ${connected ? 'on' : ''}`} title={connected ? '实时连接正常' : '正在重连后端'}>
          {connected ? <>上次扫描 {lastUpdate || '—'}<span className="next"> · 下次 {fmtCountdown(countdown)}</span></> : '连接中…'}
        </span>
        <span className="actions">
          <button className="btn ghost" onClick={runSpeedtestNow} disabled={speedRunning} title="会占满上行几十秒">
            {speedRunning ? '测速中…' : '测速'}
          </button>
          <button className="btn" onClick={scanNow} disabled={loading || !connected}>{loading ? '扫描中…' : '扫描'}</button>
        </span>
      </header>

      {error && <div className="banner">{error}</div>}

      {panel === 'speed' && (
        <section className="panel">
          <div className="panel-chart"><SpeedChart rows={speedtest?.history} /></div>
          <div className="panel-meta">
            {latest ? <>
              <div>最近一次 {fmtTime(latest.run_at)}</div>
              {/* 测速点要显出来:换了服务器数字就不可比 */}
              <div>{latest.server_sponsor}{latest.server_km ? ` · ${Math.round(latest.server_km)} km` : ''}{latest.isp ? ` · ${latest.isp}` : ''}</div>
              {speedAlert && <div className="alert-text">比平时({Math.round(typical)} Mbps)低得多 —— 可能是测的那一刻有大下载,也可能是线路问题,再测一次看看</div>}
            </> : <div>{speedtest && speedtest.available === false ? '未装 speedtest-cli' : '还没测过'}</div>}
          </div>
        </section>
      )}

      {panel === 'settings' && (
        <section className="panel settings">
          <div className="field"><label>端口扫描超时(秒)</label>
            <input type="number" min="0.5" max="10" step="0.5" value={portScanTimeout} onChange={e => setPortScanTimeout(parseFloat(e.target.value))} />
            </div>
          <div className="field"><label>并发数</label>
            <input type="number" min="5" max="100" step="5" value={portScanWorkers} onChange={e => setPortScanWorkers(parseInt(e.target.value))} />
            </div>
          <div className="field"><label>每端口重试</label>
            <input type="number" min="0" max="5" step="1" value={portScanRetries} onChange={e => setPortScanRetries(parseInt(e.target.value))} />
            </div>
          <div className="field"><label className="check"><input type="checkbox" checked={serviceScanEnabled} onChange={e => setServiceScanEnabled(e.target.checked)} />用 nmap 识别端口上的服务和版本</label></div>
          <div className="field"><label className="check"><input type="checkbox" checked={startupFullScanEnabled} onChange={e => setStartupFullScanEnabled(e.target.checked)} />打开页面时对所有在线设备做一遍端口 + 系统 + SSDP</label>
            <label>时间上限(秒)</label>
            <input type="number" min="30" max="300" step="10" value={startupFullScanBudgetSec} onChange={e => setStartupFullScanBudgetSec(parseInt(e.target.value))} /></div>
          <div className="field">
            <button className="btn ghost" onClick={scanAllDevices} disabled={!connected || onlineCount === 0}>扫描全部在线设备的端口</button>
            <small>逐台扫,找 Pi-hole(53 端口)这类服务,要几分钟</small>
          </div>
          {scanLog.length > 0 && (
            <div className="field log"><label>扫描日志</label>
              {scanLog.slice(0, 5).map((entry, i) => <div key={i} className={`log-${entry.type}`}><span>{entry.timestamp}</span> {entry.message}</div>)}
            </div>
          )}
          <p className="hint">超时调大、并发调小、重试调多:结果更准,但更慢。</p>
        </section>
      )}

      <nav className="filters">
        {activeTab === 'devices'
          ? <input type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="找设备、IP、MAC…" aria-label="搜索设备" />
          : <button className="on" onClick={() => setActiveTab('devices')}>← 回到设备</button>}
        {activeTab === 'devices' && filter !== 'all' && <button className="clear" onClick={() => setFilter('all')}>× 只看{{ online: '在线', unnamed: '未命名', offline: '离线' }[filter]},点这里看全部</button>}
        <span className="grow" />
        <button className={`btn-settings ${panel === 'settings' ? 'on' : ''}`} onClick={() => setPanel(panel === 'settings' ? null : 'settings')} aria-expanded={panel === 'settings'}>设置</button>
        <button className={activeTab === 'debug' ? 'on' : ''} onClick={() => setActiveTab(activeTab === 'debug' ? 'devices' : 'debug')}>调试</button>
      </nav>

      {activeTab === 'devices' && (
        loading && devices.length === 0 ? <div className="empty">正在扫描网络…</div> : (
          <table className="devices">
            <thead><tr>
              <Th col="ip" className="c-ip">IP</Th>
              <Th col="notes">这是谁</Th>
              <Th col="mac" className="c-mac">MAC</Th>
              <Th col="vendor" className="c-ven">厂商</Th>
              <Th col="appearance_rate" className="c-rate">在线</Th>
              <th className="c-act" aria-label="操作"></th>
            </tr></thead>
            <tbody>
              {[['需要你看一眼', attention], [attention.length ? '其余' : null, rest]].map(([title, list]) => list.length === 0 ? null : <Fragment key={title || 'all'}>
              {title && <tr className="group"><td colSpan="6">{title} {list.length}</td></tr>}
              {list.map(device => {
                const online = device.status === 'online'
                const portResults = portScanResults[device.ip]
                const isExpanded = expandedDevice === device.ip
                const rate = rateOf(device)
                const host = device.hostname && device.hostname !== 'Unknown' ? device.hostname : ''
                const editing = editingNotes === device.ip
                return (
                  <Fragment key={device.ip}>
                    <tr className={`${online ? '' : 'off'} ${isExpanded ? 'open' : ''}`}>
                      <td className="c-ip" title={device.ip}><span className="dot" />{device.ip.split('.').pop()}</td>
                      <td className="who">
                        {editing ? (
                          <input className="note-input" type="text" value={device.notes || ''} autoFocus
                                 placeholder="这是什么设备?回车保存,Esc 取消"
                                 onChange={e => setDevices(devices.map(d => d.ip === device.ip ? { ...d, notes: e.target.value } : d))}
                                 onKeyDown={e => handleNotesKeyPress(e, device.ip)}
                                 onBlur={() => setEditingNotes(null)} />
                        ) : (
                          <button className={`name ${isUnnamed(device) && online ? 'unnamed' : ''}`} onClick={() => setEditingNotes(device.ip)} title="点一下改名字(备注)">
                            {(device.notes || '').trim() || host || '未命名'}
                          </button>
                        )}
                        <div className="sub">
                          {(device.notes || '').trim() && host && <span>{host}</span>}
                          {catTag[device.category] && <span className="tag" title={catHint[device.category]}>{catTag[device.category]}</span>}
                          {portResults?.pihole && <span className="tag">Pi-hole</span>}
                        </div>
                      </td>
                      <td className="c-mac">{device.mac || '—'}</td>
                      <td className="c-ven">{device.vendor || '—'}</td>
                      <td className="c-rate">{!online
                        ? (device.last_seen ? `${ago(device.last_seen)}见过` : '离线')
                        : (rate !== null && rate < 0.995 ? `${Math.round(rate * 100)}%` : '')}</td>
                      <td className="c-act">
                        <button className="more" onClick={() => toggleExpandDevice(device.ip)} aria-expanded={isExpanded}
                                aria-label={`${device.ip} 的详情和操作`}>{isExpanded ? '×' : '⋯'}</button>
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr className="detail"><td colSpan="6">
                        <div className="detail-grid"><dl>
                          {device.os_guess && <><dt>系统</dt><dd>{device.os_guess}{device.os_accuracy ? ` (${device.os_accuracy}%)` : ''}</dd></>}
                          {!device.os_guess && device.os_last_error && <><dt>系统</dt><dd className="alert-text">上次识别失败:{device.os_last_error}</dd></>}
                          {(device.ssdp_server || device.ssdp_st) && <><dt>SSDP</dt><dd>{device.ssdp_server || device.ssdp_st}{device.ssdp_location ? ` · ${device.ssdp_location}` : ''}</dd></>}
                          {device.first_seen && <><dt>首次见到</dt><dd>{fmtTime(device.first_seen)}</dd></>}
                          {!portResults && device.last_port_scan_at && <><dt>端口</dt><dd>上次扫到 {device.last_port_scan_count} 个开放端口 · {fmtTime(device.last_port_scan_at)}</dd></>}
                        </dl>
                        <div className="acts">
                          <button className="btn ghost" onClick={() => scanPorts(device.ip)} disabled={scanningPorts[device.ip] || !online}>{scanningPorts[device.ip] ? '扫描中…' : '扫端口'}</button>
                          <button className="btn ghost" onClick={() => scanOS(device.ip)} disabled={scanningOS[device.ip] || !online}>{scanningOS[device.ip] ? '识别中…' : '识别系统'}</button>
                          <button className="btn ghost" onClick={() => scanSSDP(device.ip)} disabled={scanningSSDP[device.ip] || !online}>{scanningSSDP[device.ip] ? '发现中…' : 'SSDP 发现'}</button>
                          <button className="btn ghost" onClick={() => setEditingNotes(device.ip)}>改备注</button>
                          {portResults?.pihole && <a className="btn ghost" href={portResults.pihole.admin_url} target="_blank" rel="noopener noreferrer">Pi-hole 后台 →</a>}
                        </div></div>
                        {portResults && (
                          <div className="ports">
                            <div className="ports-head">开放端口 · {fmtTime(portResults.scan_time)}
                              {portResults.ports.some(p => p.port === 53) && !portResults.pihole && <span className="tag">DNS</span>}</div>
                            {portResults.pihole && (
                              <div className="pihole">Pi-hole{portResults.pihole.status ? ` · ${portResults.pihole.status}` : ''}
                                {portResults.pihole.domains_blocked > 0 && ` · 拦截名单 ${portResults.pihole.domains_blocked.toLocaleString()}`}
                                {portResults.pihole.queries_today > 0 && ` · 今日查询 ${portResults.pihole.queries_today.toLocaleString()}`}
                                {portResults.pihole.ads_blocked_today > 0 && ` · 今日拦截 ${portResults.pihole.ads_blocked_today.toLocaleString()}`}</div>
                            )}
                            {portResults.ports.length > 0 ? (
                              <table><tbody>
                                {portResults.ports.map(port => {
                                  const web = port.port === 80 || port.port === 443
                                  const url = `${port.port === 443 ? 'https' : 'http'}://${device.ip}${web ? '' : `:${port.port}`}`
                                  return <tr key={port.port}>
                                    <td className="mono">{web ? <a href={url} target="_blank" rel="noopener noreferrer">{port.port} →</a> : port.port}</td>
                                    <td>{port.service}</td><td className="dim">{port.details || ''}</td>
                                    <td className={port.status === 'open' ? '' : 'dim'}>{port.status}</td>
                                  </tr>
                                })}
                              </tbody></table>
                            ) : <div className="dim">没有开放端口</div>}
                          </div>
                        )}
                      </td></tr>
                    )}
                  </Fragment>
                )
              })}
              </Fragment>)}
              {visible.length === 0 && <tr><td colSpan="6" className="empty">没有符合条件的设备</td></tr>}
            </tbody>
          </table>
        )
      )}

      {activeTab === 'debug' && (
        <div className="debug">
          {dbStats ? <>
            <section>
              <h3>数据库</h3>
              <p className="stats"><span><b>{dbStats.total_scans}</b>次扫描</span><span><b>{dbStats.total_devices}</b>台设备</span><span><b>{dbStats.active_24h}</b>台 24 小时内活跃</span></p>
            </section>
            <section>
              <h3>设备历史 <button className="btn ghost" onClick={copyCSV}>复制 CSV</button> <button className="btn ghost" onClick={downloadCSV}>下载 CSV</button></h3>
              <div className="scroll"><table>
                <thead><tr><th>IP</th><th>主机名</th><th>厂商</th><th>扫描</th><th>在线</th><th>出现率</th><th>分类</th><th>备注</th></tr></thead>
                <tbody>{dbStats.devices.map((d, i) => <tr key={i}><td className="mono">{d.ip}</td><td>{d.hostname}</td><td>{d.vendor || '—'}</td><td>{d.total_scans}</td><td>{d.scans_seen_online}</td><td>{d.appearance_rate}%</td><td>{d.category}</td><td>{d.notes || '—'}</td></tr>)}</tbody>
              </table></div>
            </section>
            <section>
              <h3>分类日志(最近 50 条)</h3>
              <p className="dim">每次扫描时每台设备被分到哪一类、为什么</p>
              {catLog && catLog.log ? <div className="scroll"><table>
                <thead><tr><th>时间</th><th>IP</th><th>主机名</th><th>分类</th><th>状态</th><th>扫描</th><th>在线</th><th>出现率</th><th>原因</th></tr></thead>
                <tbody>{catLog.log.slice(0, 50).map((e, i) => <tr key={i}><td className="mono">{fmtTime(e.timestamp)}</td><td className="mono">{e.ip}</td><td>{e.hostname}</td><td>{e.category}</td><td>{e.device_status}</td><td>{e.total_scans}</td><td>{e.scans_seen_online}</td><td>{(e.appearance_rate * 100).toFixed(1)}%</td><td className="dim">{e.reason}</td></tr>)}</tbody>
              </table></div> : <div className="dim">加载中…</div>}
            </section>
          </> : <div className="empty">加载中…</div>}
        </div>
      )}
    </div>
  )
}

export default App
