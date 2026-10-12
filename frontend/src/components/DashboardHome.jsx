import { useEffect, useState } from 'react'
import { getDashboardStats } from '../api/dashboard'
import { getErrorMessage } from '../api/errors'
import SalesTrendChart from './SalesTrendChart'
import SalesByCategoryChart from './SalesByCategoryChart'
import { formatCurrency, formatNumber } from '../utils/format'

function KpiIcon({ name }) {
  const paths = {
    valuation: (
      <>
        <path d="M3 8l9-5 9 5-9 5-9-5z" />
        <path d="M3 12l9 5 9-5" />
        <path d="M3 16l9 5 9-5" />
      </>
    ),
    revenue: (
      <>
        <path d="M4 19V10M11 19V4M18 19v-6" />
      </>
    ),
    profit: (
      <>
        <path d="M3 17l6-6 4 4 8-8" />
        <path d="M15 7h6v6" />
      </>
    ),
    alert: (
      <>
        <path d="M12 3l10 18H2L12 3z" />
        <path d="M12 10v4M12 17h.01" />
      </>
    ),
  }
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      {paths[name]}
    </svg>
  )
}

const PERIODS = [
  { key: 'today', label: 'Today' },
  { key: 'week', label: 'This Week' },
  { key: 'month', label: 'This Month' },
]

export default function DashboardHome({ onNavigateToInventory }) {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [period, setPeriod] = useState('today')

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError('')
      try {
        const data = await getDashboardStats()
        if (!cancelled) setStats(data)
      } catch (err) {
        if (!cancelled) setError(getErrorMessage(err, 'Could not load dashboard stats. Please try again.'))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [])

  if (loading) {
    return <p className="muted-text">Loading dashboard…</p>
  }

  if (error) {
    return <p className="error-text">{error}</p>
  }

  if (!stats) return null

  const reorderAlerts = stats.low_stock_count + stats.out_of_stock_count

  return (
    <div className="dashboard-home">
      <div className="kpi-grid">
        <div className="kpi-card">
          <div className="kpi-icon"><KpiIcon name="valuation" /></div>
          <div className="kpi-label">Inventory Valuation</div>
          <div className="kpi-value">{formatCurrency(stats.inventory_cost_valuation)}</div>
          <div className="kpi-sub">Retail value {formatCurrency(stats.inventory_retail_valuation)}</div>
        </div>

        <div className="kpi-card kpi-card-wide">
          <div className="kpi-card-header">
            <div className="kpi-icon"><KpiIcon name="revenue" /></div>
            <div className="tab-bar tab-bar-sm period-toggle">
              {PERIODS.map((p) => (
                <button
                  key={p.key}
                  type="button"
                  className={`tab-btn ${period === p.key ? 'active' : ''}`}
                  onClick={() => setPeriod(p.key)}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>
          <div className="kpi-revenue-profit-grid">
            <div>
              <div className="kpi-label">Revenue</div>
              <div className="kpi-value">{formatCurrency(stats.period_stats[period].revenue)}</div>
              <div className="kpi-sub">{formatNumber(stats.period_stats[period].units_sold)} units sold</div>
            </div>
            <div>
              <div className="kpi-label">Profit</div>
              <div className="kpi-value">{formatCurrency(stats.period_stats[period].profit)}</div>
              <div className="kpi-sub">{formatNumber(stats.product_count)} products tracked</div>
            </div>
          </div>
        </div>

        <div className={`kpi-card ${reorderAlerts > 0 ? 'kpi-card-alert' : ''}`}>
          <div className="kpi-icon"><KpiIcon name="alert" /></div>
          <div className="kpi-label">Reorder Alerts</div>
          <div className="kpi-value">{formatNumber(reorderAlerts)}</div>
          <div className="kpi-sub">
            {formatNumber(stats.low_stock_count)} low · {formatNumber(stats.out_of_stock_count)} out
          </div>
          {reorderAlerts > 0 && (
            <button
              type="button"
              className="btn-secondary kpi-action"
              onClick={() => onNavigateToInventory({ filter: 'low_stock' })}
            >
              View items
            </button>
          )}
        </div>
      </div>

      <div className="dashboard-grid">
        <div className="dashboard-panel dashboard-panel-chart">
          <h3>Sales — last 30 days</h3>
          <SalesTrendChart data={stats.sales_over_time} />
        </div>

        <div className="dashboard-panel dashboard-panel-attention">
          <h3>Needs attention</h3>
          {stats.low_stock_items.length === 0 ? (
            <p className="muted-text">✅ All stocked up — nothing needs reordering.</p>
          ) : (
            <ul className="attention-list">
              {stats.low_stock_items.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    className="attention-item"
                    onClick={() => onNavigateToInventory({ editProductId: item.id })}
                  >
                    <span
                      className={`status-dot ${item.quantity_in_stock === 0 ? 'status-dot-danger' : 'status-dot-warning'}`}
                    />
                    <span className="attention-name">{item.name}</span>
                    <span className="attention-qty">
                      {item.quantity_in_stock} / {item.reorder_level} in stock
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="dashboard-grid">
        <div className="dashboard-panel">
          <h3>Top products</h3>
          {stats.top_products.length === 0 ? (
            <p className="muted-text">No sales recorded yet.</p>
          ) : (
            <ul className="top-products-list">
              {stats.top_products.map((p) => (
                <li key={p.name}>
                  <span className="top-product-name">{p.name}</span>
                  <span className="top-product-units">{formatNumber(p.units)} sold</span>
                  <span className="top-product-revenue">{formatCurrency(p.revenue)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="dashboard-panel">
          <h3>Sales by category</h3>
          <SalesByCategoryChart data={stats.sales_by_category} />
        </div>
      </div>
    </div>
  )
}
