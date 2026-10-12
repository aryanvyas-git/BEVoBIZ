// Chart libraries (recharts) set colors as raw SVG attributes rather than
// through the CSS cascade, so `var(--color-*)` custom properties don't
// resolve there — these mirror the palette in index.css as literal hex
// values for chart use only. Keep the two in sync when re-theming.
export const CHART_PRIMARY = '#4caf6d'
export const CHART_PRIMARY_LIGHT = '#e3f4e9'
export const CHART_COLORS = [
  '#4caf6d',
  '#f2c230',
  '#111111',
  '#7aa8f0',
  '#2f7a48',
  '#b8790a',
  '#6b7094',
  '#e5484d',
]
export const CHART_GRID = '#dce1f5'
export const CHART_MUTED_TEXT = '#5b5f76'
export const CHART_TOOLTIP_BORDER = '#dce1f5'
