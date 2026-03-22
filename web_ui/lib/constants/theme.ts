/**
 * Centralized theme constants for the EOS web UI
 */

// Port type colors
export const PORT_COLORS = {
  device: '#3b82f6', // blue-500
  resource: '#10b981', // emerald-500
  parameter: '#a855f7', // purple-500
  main: {
    bg: '#3b82f6',
    border: 'white',
  },
} as const;

// Dark theme edge colors (lighter for better visibility)
export const EDGE_COLORS_DARK = {
  dependency: '#e2e8f0', // slate-200
  device: '#fef08a', // yellow-200
  resource: '#a7f3d0', // emerald-200
  parameter: '#e9d5ff', // purple-200
} as const;

// Light theme edge colors
export const EDGE_COLORS_LIGHT = {
  dependency: '#000000', // black
  device: '#3b82f6', // blue-500
  resource: '#10b981', // emerald-500
  parameter: '#a855f7', // purple-500
} as const;

// Badge/tag color classes for light/dark mode
export const BADGE_CLASSES = {
  device: 'bg-blue-50 dark:bg-yellow-900/30 text-blue-600 dark:text-yellow-400',
  resource: 'bg-green-50 dark:bg-green-900/30 text-green-600 dark:text-green-400',
  parameter: 'bg-purple-50 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400',
} as const;

// Constraint tag colors
export const CONSTRAINT_COLORS = {
  blue: 'bg-blue-100 dark:bg-yellow-900/30 text-blue-700 dark:text-yellow-400',
  green: 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400',
} as const;

// Preset colors for color picker
export const PRESET_COLORS = [
  { name: 'Blue', value: '#3b82f6' },
  { name: 'Purple', value: '#8b5cf6' },
  { name: 'Pink', value: '#ec4899' },
  { name: 'Red', value: '#ef4444' },
  { name: 'Orange', value: '#f97316' },
  { name: 'Yellow', value: '#eab308' },
  { name: 'Green', value: '#22c55e' },
  { name: 'Teal', value: '#14b8a6' },
  { name: 'Cyan', value: '#06b6d4' },
  { name: 'Indigo', value: '#6366f1' },
  { name: 'Gray', value: '#6b7280' },
  { name: 'Slate', value: '#64748b' },
] as const;

// Editor grid and layout
export const EDITOR_LAYOUT = {
  gridSize: 20,
  horizontalSpacing: 350,
  verticalSpacing: 150,
  startX: 100,
  startY: 100,
} as const;

// Port handle sizes
export const PORT_SIZES = {
  small: 8,
  large: 12,
} as const;

// Timing constants
export const TIMING = {
  toastDuration: 8000, // ms
  debounceDelay: 500, // ms
  allocationTimeout: 600, // seconds
} as const;

/**
 * Get edge colors based on theme
 */
export function getEdgeColors(isDark: boolean) {
  return isDark ? EDGE_COLORS_DARK : EDGE_COLORS_LIGHT;
}

/**
 * Get badge classes for a port type
 */
export function getBadgeClass(type: 'device' | 'resource' | 'parameter'): string {
  return BADGE_CLASSES[type];
}

/**
 * Adjust color brightness (positive = lighter, negative = darker)
 */
export function adjustColorBrightness(color: string, percent: number): string {
  const num = parseInt(color.replace('#', ''), 16);
  const amt = Math.round(2.55 * percent);
  const R = Math.max(0, Math.min(255, (num >> 16) + amt));
  const G = Math.max(0, Math.min(255, ((num >> 8) & 0x00ff) + amt));
  const B = Math.max(0, Math.min(255, (num & 0x0000ff) + amt));
  return `#${((1 << 24) | (R << 16) | (G << 8) | B).toString(16).slice(1)}`;
}
