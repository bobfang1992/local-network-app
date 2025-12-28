import { useState, useEffect, useRef } from 'react'
import './App.css'

function App() {
  const [devices, setDevices] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [lastUpdate, setLastUpdate] = useState(null)
  const [connected, setConnected] = useState(false)
  const [nextScan, setNextScan] = useState(null)
  const [scanInterval, setScanInterval] = useState(30)
  const [countdown, setCountdown] = useState(null)
  const [scanLog, setScanLog] = useState([])
  const [activeTab, setActiveTab] = useState('devices')
  const [dbStats, setDbStats] = useState(null)
  const [editingNotes, setEditingNotes] = useState(null) // IP of device being edited
  const wsRef = useRef(null)
  const reconnectTimeoutRef = useRef(null)
  const countdownIntervalRef = useRef(null)

  const connectWebSocket = () => {
    try {
      const ws = new WebSocket('ws://localhost:8000/ws')
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
            setLastUpdate(date.toLocaleTimeString())
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

  const fetchDbStats = async () => {
    try {
      const response = await fetch('http://localhost:8000/api/database/stats')
      const data = await response.json()
      setDbStats(data)
    } catch (err) {
      console.error('Failed to fetch database stats:', err)
    }
  }

  const updateNotes = async (ip, notes) => {
    try {
      const response = await fetch(`http://localhost:8000/api/devices/${ip}/notes`, {
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

  const handleNotesKeyPress = (e, ip, notes) => {
    if (e.key === 'Enter') {
      updateNotes(ip, notes)
    } else if (e.key === 'Escape') {
      setEditingNotes(null)
    }
  }

  const generateCSV = () => {
    if (!dbStats || !dbStats.devices) return ''

    const headers = ['IP', 'Hostname', 'Total Scans', 'Scans Online', 'Appearance Rate (%)', 'Category', 'Notes']
    const rows = dbStats.devices.map(d => [
      d.ip,
      d.hostname,
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
    alert('CSV copied to clipboard!')
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
  }

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
      const interval = setInterval(fetchDbStats, 5000) // Refresh every 5 seconds
      return () => clearInterval(interval)
    }
  }, [activeTab])

  return (
    <div className="container">
      <div className="header">
        <h1>Local Network Devices</h1>
        <hr />
      </div>

      {error && (
        <div className="error-banner mb4">
          {error}
        </div>
      )}

      <div className="two-column-layout">
        {/* Left column: Main content with tabs */}
        <div className="main-content">
          {/* Tabs */}
          <div className="tabs">
            <button
              className={`tab ${activeTab === 'devices' ? 'active' : ''}`}
              onClick={() => setActiveTab('devices')}
            >
              Devices
            </button>
            <button
              className={`tab ${activeTab === 'debug' ? 'active' : ''}`}
              onClick={() => setActiveTab('debug')}
            >
              Debug
            </button>
          </div>

          {/* Devices Tab */}
          {activeTab === 'devices' && (
            <>
              {loading && devices.length === 0 ? (
                <div className="loading">
                  <p>Scanning network...</p>
                </div>
              ) : (
                <table className="table">
                  <thead>
                    <tr>
                      <th>Hostname</th>
                      <th>IP Address</th>
                      <th>MAC Address</th>
                      <th>Status</th>
                      <th>Notes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {devices.map((device, index) => {
                      const rowClasses = [
                        'device-row',
                        device.device_status || '',
                        device.device_category ? `category-${device.device_category}` : ''
                      ].filter(Boolean).join(' ')

                      return (
                        <tr key={index} className={rowClasses}>
                          <td className="hostname-cell">
                            {device.device_status === 'new' && <span className="badge badge-new">NEW</span>}
                            {device.device_status === 'offline' && <span className="badge badge-offline">OFFLINE</span>}
                            {device.device_status !== 'new' && device.device_status !== 'offline' && device.device_category === 'regular' && (
                              <span className="badge badge-regular">REGULAR</span>
                            )}
                            {device.device_status !== 'new' && device.device_status !== 'offline' && device.device_category === 'rare' && (
                              <span className="badge badge-rare">RARE</span>
                            )}
                            {device.hostname}
                          </td>
                          <td>{device.ip}</td>
                          <td>{device.mac}</td>
                          <td>{device.status}</td>
                          <td>
                            {editingNotes === device.ip ? (
                              <input
                                type="text"
                                value={device.notes || ''}
                                onChange={(e) => {
                                  // Update local state immediately for responsiveness
                                  const newDevices = [...devices]
                                  newDevices[index].notes = e.target.value
                                  setDevices(newDevices)
                                }}
                                onKeyDown={(e) => handleNotesKeyPress(e, device.ip, device.notes)}
                                onBlur={() => setEditingNotes(null)}
                                autoFocus
                                placeholder="Type note and press Enter..."
                                style={{
                                  width: '100%',
                                  border: '1px solid #000',
                                  padding: '0.25rem',
                                  fontFamily: 'inherit',
                                  fontSize: '0.875rem'
                                }}
                              />
                            ) : (
                              <div
                                onClick={() => setEditingNotes(device.ip)}
                                style={{
                                  cursor: 'pointer',
                                  padding: '0.25rem',
                                  minHeight: '1.5rem',
                                  color: device.notes ? '#000' : '#999'
                                }}
                              >
                                {device.notes || 'Click to add notes...'}
                              </div>
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              )}
            </>
          )}

          {/* Debug Tab */}
          {activeTab === 'debug' && (
            <div className="debug-panel">
              {dbStats ? (
                <>
                  <div className="debug-section">
                    <h3>Database Statistics</h3>
                    <div className="debug-stats">
                      <div className="debug-stat">
                        <div className="debug-stat-label">Total Scans</div>
                        <div className="debug-stat-value">{dbStats.total_scans}</div>
                      </div>
                      <div className="debug-stat">
                        <div className="debug-stat-label">Known Devices</div>
                        <div className="debug-stat-value">{dbStats.total_devices}</div>
                      </div>
                      <div className="debug-stat">
                        <div className="debug-stat-label">Active (24h)</div>
                        <div className="debug-stat-value">{dbStats.active_24h}</div>
                      </div>
                    </div>
                  </div>

                  <div className="debug-section">
                    <h3>Device History</h3>
                    <div className="mb2">
                      <button onClick={copyCSV} className="btn-classic" style={{ marginRight: '0.5rem' }}>
                        Copy CSV
                      </button>
                      <button onClick={downloadCSV} className="btn-classic">
                        Download CSV
                      </button>
                    </div>
                    <table className="debug-table">
                      <thead>
                        <tr>
                          <th>IP</th>
                          <th>Hostname</th>
                          <th>Total Scans</th>
                          <th>Scans Online</th>
                          <th>Appearance %</th>
                          <th>Category</th>
                          <th>Notes</th>
                        </tr>
                      </thead>
                      <tbody>
                        {dbStats.devices.map((device, index) => (
                          <tr key={index}>
                            <td>{device.ip}</td>
                            <td>{device.hostname}</td>
                            <td>{device.total_scans}</td>
                            <td>{device.scans_seen_online}</td>
                            <td>{device.appearance_rate}%</td>
                            <td>{device.category}</td>
                            <td>{device.notes || '-'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              ) : (
                <div className="loading">Loading database stats...</div>
              )}
            </div>
          )}
        </div>

        {/* Right column: Status panel */}
        <div className="status-panel">
          <h2 className="panel-title">Status</h2>

          <div className="status-section">
            <div className="status-label">Connection</div>
            <div className="status-value">
              {connected ? (
                <span className="status-connected">Connected</span>
              ) : (
                <span className="status-disconnected">Connecting...</span>
              )}
            </div>
          </div>

          <div className="status-section">
            <div className="status-label">Devices</div>
            <div className="status-value">
              {devices.length} device{devices.length !== 1 ? 's' : ''} found
            </div>
          </div>

          {lastUpdate && (
            <div className="status-section">
              <div className="status-label">Last Scan</div>
              <div className="status-value">{lastUpdate}</div>
            </div>
          )}

          <div className="status-section">
            <button onClick={scanNow} disabled={loading || !connected} className="btn-classic w-full">
              {loading ? 'Scanning...' : 'Scan Now →'}
            </button>
          </div>

          {connected && (
            <div className="status-section">
              <div className="status-label">Next Scan</div>
              <div className="progress-bar-container">
                <div
                  className="progress-bar-fill"
                  style={{
                    width: countdown !== null
                      ? `${((scanInterval - countdown) / scanInterval) * 100}%`
                      : '0%'
                  }}
                ></div>
              </div>
              <div className="moon-gray mt1">
                {countdown !== null ? (
                  <>In {countdown} seconds</>
                ) : (
                  <>Waiting for first scan...</>
                )}
              </div>
            </div>
          )}

          {scanLog.length > 0 && (
            <div className="status-section">
              <div className="status-label">Scan Log</div>
              <div className="scan-log-panel">
                {scanLog.slice(0, 5).map((entry, index) => (
                  <div key={index} className={`log-entry ${entry.type}`}>
                    <span className="log-time">{entry.timestamp}</span>
                    <div className="log-message">{entry.message}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="status-section">
            <div className="status-label">Color Legend</div>
            <div className="color-legend">
              <div className="legend-item">
                <div className="legend-color" style={{ backgroundColor: '#e8f5e9', borderColor: '#4caf50' }}></div>
                <div className="legend-label">NEW - First time seen</div>
              </div>
              <div className="legend-item">
                <div className="legend-color" style={{ backgroundColor: '#e3f2fd', borderColor: '#42a5f5' }}></div>
                <div className="legend-label">REGULAR - Seen in &gt;70% of scans</div>
              </div>
              <div className="legend-item">
                <div className="legend-color" style={{ backgroundColor: '#fff8e1', borderColor: '#ffb74d' }}></div>
                <div className="legend-label">RARE - Seen in &lt;30% of scans</div>
              </div>
              <div className="legend-item">
                <div className="legend-color" style={{ backgroundColor: '#fafafa', borderColor: '#e0e0e0' }}></div>
                <div className="legend-label">OFFLINE - Not responding</div>
              </div>
              <div className="legend-item">
                <div className="legend-color" style={{ backgroundColor: '#f0f4f8', borderColor: '#e0e0e0' }}></div>
                <div className="legend-label">Regular device offline</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default App
