// 级别/状态标签映射
export const SEVERITY_TYPE = {
  灾难: 'danger',
  严重: 'danger',
  一般严重: 'warning',
  警告: 'warning',
  信息: 'info',
  未分类: 'info',
}

export const ANALYSIS_STATUS = {
  pending: { label: '待分析', type: 'info' },
  processing: { label: '分析中', type: 'warning' },
  success: { label: '分析成功', type: 'success' },
  failed: { label: '分析失败', type: 'danger' },
}

export const ALERT_STATUS = {
  problem: { label: '未恢复', type: 'danger' },
  resolved: { label: '已恢复', type: 'success' },
}

export function severityTag(sev) {
  return SEVERITY_TYPE[sev] || 'info'
}

export function analysisTag(status) {
  return ANALYSIS_STATUS[status] || { label: status, type: 'info' }
}

export function alertTag(status) {
  return ALERT_STATUS[status] || { label: status, type: 'info' }
}

export function fmtTime(t) {
  if (!t) return '-'
  const d = new Date(t)
  if (Number.isNaN(d.getTime())) return t
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}
