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
  const [catLog, setCatLog] = useState(null)
  const [editingNotes, setEditingNotes] = useState(null) // IP of device being edited
  const [sortColumn, setSortColumn] = useState('ip')
  const [sortDirection, setSortDirection] = useState('asc')
  const [expandedDevice, setExpandedDevice] = useState(null) // IP of expanded device
  const [portScanResults, setPortScanResults] = useState({}) // Map of IP -> port scan results
  const [scanningPorts, setScanningPorts] = useState({}) // Map of IP -> scanning status
  const [portScanTimeout, setPortScanTimeout] = useState(2.0)
  const [portScanWorkers, setPortScanWorkers] = useState(20)
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

  const fetchCatLog = async () => {
    try {
      const response = await fetch('http://localhost:8000/api/categorization/log?limit=50')
      const data = await response.json()
      setCatLog(data)
    } catch (err) {
      console.error('Failed to fetch categorization log:', err)
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

  const handleNotesKeyPress = (e, ip) => {
    if (e.key === 'Enter') {
      // Get the current value from the input field
      updateNotes(ip, e.target.value)
    } else if (e.key === 'Escape') {
      setEditingNotes(null)
    }
  }

  const scanPorts = async (ip) => {
    try {
      // Set scanning state
      setScanningPorts(prev => ({ ...prev, [ip]: true }))

      const response = await fetch(`http://localhost:8000/api/devices/${ip}/scan-ports?timeout=${portScanTimeout}&max_workers=${portScanWorkers}`, {
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
      }
    } catch (err) {
      console.error('Failed to scan ports:', err)
    } finally {
      setScanningPorts(prev => ({ ...prev, [ip]: false }))
    }
  }

  const scanAllDevices = async () => {
    const onlineDevices = devices.filter(d => d.status === 'online')

    if (onlineDevices.length === 0) {
      alert('No online devices to scan')
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
      fetchCatLog()
      const interval = setInterval(() => {
        fetchDbStats()
        fetchCatLog()
      }, 5000) // Refresh every 5 seconds
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
                      <th onClick={() => handleSort('hostname')} style={{ cursor: 'pointer' }}>
                        Hostname {sortColumn === 'hostname' && (sortDirection === 'asc' ? '↑' : '↓')}
                      </th>
                      <th onClick={() => handleSort('ip')} style={{ cursor: 'pointer' }}>
                        IP Address {sortColumn === 'ip' && (sortDirection === 'asc' ? '↑' : '↓')}
                      </th>
                      <th onClick={() => handleSort('mac')} style={{ cursor: 'pointer' }}>
                        MAC Address {sortColumn === 'mac' && (sortDirection === 'asc' ? '↑' : '↓')}
                      </th>
                      <th onClick={() => handleSort('status')} style={{ cursor: 'pointer' }}>
                        Status {sortColumn === 'status' && (sortDirection === 'asc' ? '↑' : '↓')}
                      </th>
                      <th onClick={() => handleSort('notes')} style={{ cursor: 'pointer' }}>
                        Notes {sortColumn === 'notes' && (sortDirection === 'asc' ? '↑' : '↓')}
                      </th>
                      <th style={{ width: '120px' }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {getSortedDevices().map((device) => {
                      const category = device.category || 'unknown'
                      const rowClasses = ['device-row', `category-${category}`].filter(Boolean).join(' ')

                      const portResults = portScanResults[device.ip]
                      const isScanning = scanningPorts[device.ip]
                      const isExpanded = expandedDevice === device.ip

                      return (
                        <>
                          <tr key={device.ip} className={rowClasses}>
                            <td className="hostname-cell">
                              {category === 'new' && <span className="badge badge-new">NEW</span>}
                              {category === 'offline' && <span className="badge badge-offline">OFFLINE</span>}
                              {category === 'regular' && <span className="badge badge-regular">REGULAR</span>}
                              {category === 'occasional' && <span className="badge badge-occasional">OCCASIONAL</span>}
                              {category === 'rare' && <span className="badge badge-rare">RARE</span>}
                              {portResults?.pihole && (
                                <span className="badge" style={{
                                  backgroundColor: '#1976d2',
                                  color: '#fff',
                                  borderColor: '#1976d2'
                                }}>
                                  🛡️ PI-HOLE
                                </span>
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
                                    // Find and update device by IP (not index) to work with sorted tables
                                    const newDevices = devices.map(d =>
                                      d.ip === device.ip ? { ...d, notes: e.target.value } : d
                                    )
                                    setDevices(newDevices)
                                  }}
                                  onKeyDown={(e) => handleNotesKeyPress(e, device.ip)}
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
                            <td>
                              <button
                                onClick={() => scanPorts(device.ip)}
                                disabled={isScanning || device.status === 'offline'}
                                className="btn-classic"
                                style={{
                                  fontSize: '0.75rem',
                                  padding: '0.25rem 0.5rem',
                                  marginRight: '0.25rem',
                                  marginBottom: '0.25rem'
                                }}
                              >
                                {isScanning ? 'Scanning...' : 'Scan Ports'}
                              </button>
                              {portResults && (
                                <button
                                  onClick={() => toggleExpandDevice(device.ip)}
                                  className="btn-classic"
                                  style={{
                                    fontSize: '0.75rem',
                                    padding: '0.25rem 0.5rem',
                                    backgroundColor: isExpanded ? '#666' : '#000',
                                    marginRight: '0.25rem',
                                    marginBottom: '0.25rem'
                                  }}
                                >
                                  {isExpanded ? '▼' : '▶'} {portResults.ports.length}
                                </button>
                              )}
                              {portResults?.pihole && (
                                <a
                                  href={portResults.pihole.admin_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="btn-classic"
                                  style={{
                                    fontSize: '0.75rem',
                                    padding: '0.25rem 0.5rem',
                                    backgroundColor: '#1976d2',
                                    textDecoration: 'none',
                                    display: 'inline-block'
                                  }}
                                >
                                  Pi-hole Admin →
                                </a>
                              )}
                            </td>
                          </tr>
                          {isExpanded && portResults && (
                            <tr key={`${device.ip}-ports`}>
                              <td colSpan="6" style={{ padding: '1rem', backgroundColor: '#fafafa' }}>
                                <div style={{ fontSize: '0.875rem', marginBottom: '0.5rem', fontWeight: 500 }}>
                                  Open Ports on {device.ip}
                                  <span style={{ color: '#666', fontWeight: 400, marginLeft: '0.5rem' }}>
                                    (Scanned: {new Date(portResults.scan_time).toLocaleString()})
                                  </span>
                                  {portResults.ports.some(p => p.port === 53) && !portResults.pihole && (
                                    <span style={{
                                      marginLeft: '0.5rem',
                                      padding: '0.25rem 0.5rem',
                                      backgroundColor: '#e3f2fd',
                                      color: '#1565c0',
                                      fontSize: '0.75rem',
                                      fontWeight: 500,
                                      borderRadius: '3px'
                                    }}>
                                      🔍 DNS Server
                                    </span>
                                  )}
                                  {portResults.pihole && (
                                    <span style={{
                                      marginLeft: '0.5rem',
                                      padding: '0.25rem 0.5rem',
                                      backgroundColor: '#1976d2',
                                      color: '#fff',
                                      fontSize: '0.75rem',
                                      fontWeight: 500,
                                      borderRadius: '3px'
                                    }}>
                                      🛡️ Pi-hole Detected!
                                    </span>
                                  )}
                                </div>
                                {portResults.pihole && (
                                  <div style={{
                                    backgroundColor: '#e3f2fd',
                                    padding: '0.75rem',
                                    marginBottom: '0.75rem',
                                    borderLeft: '3px solid #1976d2',
                                    fontSize: '0.75rem'
                                  }}>
                                    <div style={{ fontWeight: 500, marginBottom: '0.5rem' }}>
                                      Pi-hole Information:
                                    </div>
                                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
                                      {portResults.pihole.domains_blocked > 0 && (
                                        <div>Domains Blocked: <strong>{portResults.pihole.domains_blocked.toLocaleString()}</strong></div>
                                      )}
                                      {portResults.pihole.queries_today > 0 && (
                                        <div>Queries Today: <strong>{portResults.pihole.queries_today.toLocaleString()}</strong></div>
                                      )}
                                      {portResults.pihole.ads_blocked_today > 0 && (
                                        <div>Ads Blocked Today: <strong>{portResults.pihole.ads_blocked_today.toLocaleString()}</strong></div>
                                      )}
                                      {portResults.pihole.status && (
                                        <div>Status: <strong style={{ color: portResults.pihole.status === 'enabled' ? '#2e7d32' : '#666' }}>
                                          {portResults.pihole.status}
                                        </strong></div>
                                      )}
                                    </div>
                                    <div style={{ marginTop: '0.5rem' }}>
                                      <a
                                        href={portResults.pihole.admin_url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        style={{ color: '#1976d2', fontWeight: 500, textDecoration: 'underline' }}
                                      >
                                        Open Pi-hole Admin →
                                      </a>
                                    </div>
                                  </div>
                                )}
                                {portResults.ports.length > 0 ? (
                                  <table style={{ width: '100%', fontSize: '0.75rem' }}>
                                    <thead>
                                      <tr style={{ borderBottom: '1px solid #ddd' }}>
                                        <th style={{ padding: '0.25rem', textAlign: 'left', width: '80px' }}>Port</th>
                                        <th style={{ padding: '0.25rem', textAlign: 'left' }}>Service</th>
                                        <th style={{ padding: '0.25rem', textAlign: 'left', width: '80px' }}>Status</th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {portResults.ports.map((port) => {
                                        const isWebPort = port.port === 80 || port.port === 443
                                        const protocol = port.port === 443 ? 'https' : 'http'
                                        const url = `${protocol}://${device.ip}${port.port === 80 || port.port === 443 ? '' : `:${port.port}`}`

                                        return (
                                          <tr key={port.port} style={{ borderBottom: '1px solid #eee' }}>
                                            <td style={{ padding: '0.25rem', fontFamily: 'monospace' }}>
                                              {isWebPort ? (
                                                <a
                                                  href={url}
                                                  target="_blank"
                                                  rel="noopener noreferrer"
                                                  style={{
                                                    color: '#1565c0',
                                                    textDecoration: 'underline',
                                                    cursor: 'pointer'
                                                  }}
                                                >
                                                  {port.port} →
                                                </a>
                                              ) : (
                                                port.port
                                              )}
                                            </td>
                                            <td style={{ padding: '0.25rem' }}>
                                              {isWebPort ? (
                                                <a
                                                  href={url}
                                                  target="_blank"
                                                  rel="noopener noreferrer"
                                                  style={{
                                                    color: '#1565c0',
                                                    textDecoration: 'none'
                                                  }}
                                                >
                                                  {port.service}
                                                </a>
                                              ) : (
                                                port.service
                                              )}
                                            </td>
                                            <td style={{ padding: '0.25rem' }}>
                                              <span style={{
                                                color: port.status === 'open' ? '#2e7d32' : '#999',
                                                fontWeight: 500
                                              }}>
                                                {port.status}
                                              </span>
                                            </td>
                                          </tr>
                                        )
                                      })}
                                    </tbody>
                                  </table>
                                ) : (
                                  <div style={{ color: '#666', padding: '1rem' }}>
                                    No open ports found
                                  </div>
                                )}
                              </td>
                            </tr>
                          )}
                        </>
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

                  <div className="debug-section">
                    <h3>Categorization Log (Last 50 Entries)</h3>
                    <p style={{ fontSize: '0.75rem', color: '#666', marginBottom: '1rem' }}>
                      Shows how each device was categorized at each scan. This helps debug why devices are showing certain colors.
                    </p>
                    {catLog && catLog.log ? (
                      <table className="debug-table">
                        <thead>
                          <tr>
                            <th>Timestamp</th>
                            <th>IP</th>
                            <th>Hostname</th>
                            <th>Category</th>
                            <th>Status</th>
                            <th>Total Scans</th>
                            <th>Online</th>
                            <th>Rate</th>
                            <th>Reason</th>
                          </tr>
                        </thead>
                        <tbody>
                          {catLog.log.slice(0, 50).map((entry, index) => (
                            <tr key={index}>
                              <td>{new Date(entry.timestamp).toLocaleTimeString()}</td>
                              <td>{entry.ip}</td>
                              <td>{entry.hostname}</td>
                              <td>{entry.category}</td>
                              <td>{entry.device_status}</td>
                              <td>{entry.total_scans}</td>
                              <td>{entry.scans_seen_online}</td>
                              <td>{(entry.appearance_rate * 100).toFixed(1)}%</td>
                              <td style={{ fontSize: '0.65rem' }}>{entry.reason}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    ) : (
                      <div>Loading categorization log...</div>
                    )}
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

          <div className="status-section">
            <button
              onClick={scanAllDevices}
              disabled={!connected || devices.filter(d => d.status === 'online').length === 0}
              className="btn-classic w-full"
              style={{ backgroundColor: '#1565c0' }}
            >
              Scan All Ports →
            </button>
            <div style={{ fontSize: '0.625rem', color: '#666', marginTop: '0.5rem' }}>
              Scans ports on all online devices to find services like Pi-hole (DNS on port 53)
            </div>
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
            <div className="status-label">Port Scan Settings</div>
            <div style={{ marginBottom: '0.75rem' }}>
              <label style={{ fontSize: '0.75rem', color: '#666', display: 'block', marginBottom: '0.25rem' }}>
                Timeout (seconds)
              </label>
              <input
                type="number"
                min="0.5"
                max="10"
                step="0.5"
                value={portScanTimeout}
                onChange={(e) => setPortScanTimeout(parseFloat(e.target.value))}
                style={{
                  width: '100%',
                  padding: '0.25rem',
                  border: '1px solid #ddd',
                  fontSize: '0.875rem',
                  fontFamily: 'inherit'
                }}
              />
              <div style={{ fontSize: '0.625rem', color: '#999', marginTop: '0.25rem' }}>
                Higher = more reliable, slower
              </div>
            </div>
            <div style={{ marginBottom: '0.75rem' }}>
              <label style={{ fontSize: '0.75rem', color: '#666', display: 'block', marginBottom: '0.25rem' }}>
                Concurrent Workers
              </label>
              <input
                type="number"
                min="5"
                max="100"
                step="5"
                value={portScanWorkers}
                onChange={(e) => setPortScanWorkers(parseInt(e.target.value))}
                style={{
                  width: '100%',
                  padding: '0.25rem',
                  border: '1px solid #ddd',
                  fontSize: '0.875rem',
                  fontFamily: 'inherit'
                }}
              />
              <div style={{ fontSize: '0.625rem', color: '#999', marginTop: '0.25rem' }}>
                Lower = more reliable, slower
              </div>
            </div>
          </div>

          <div className="status-section">
            <div className="status-label">Color Legend</div>
            <div className="color-legend">
              <div className="legend-item">
                <div className="legend-color" style={{ backgroundColor: '#e8f5e9', borderColor: '#4caf50' }}></div>
                <div className="legend-label">NEW - First 3 scans</div>
              </div>
              <div className="legend-item">
                <div className="legend-color" style={{ backgroundColor: '#e3f2fd', borderColor: '#42a5f5' }}></div>
                <div className="legend-label">REGULAR - Appears &gt;70%</div>
              </div>
              <div className="legend-item">
                <div className="legend-color" style={{ backgroundColor: '#fff9e6', borderColor: '#ffb74d' }}></div>
                <div className="legend-label">OCCASIONAL - Appears 30-70%</div>
              </div>
              <div className="legend-item">
                <div className="legend-color" style={{ backgroundColor: '#fff3e0', borderColor: '#ff9800' }}></div>
                <div className="legend-label">RARE - Appears &lt;30%</div>
              </div>
              <div className="legend-item">
                <div className="legend-color" style={{ backgroundColor: '#fafafa', borderColor: '#ccc' }}></div>
                <div className="legend-label">OFFLINE - Not responding</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default App
