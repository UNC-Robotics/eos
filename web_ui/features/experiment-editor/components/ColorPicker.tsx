'use client';

import { memo, useState } from 'react';
import { X } from 'lucide-react';
import { PRESET_COLORS } from '@/lib/constants/theme';

interface ColorPickerProps {
  currentColor?: string;
  onColorSelect: (color: string) => void;
  onClose: () => void;
  position?: { x: number; y: number };
}

const ColorPickerComponent = ({ currentColor, onColorSelect, onClose, position }: ColorPickerProps) => {
  const [customColor, setCustomColor] = useState(currentColor || '#3b82f6');

  const handlePresetClick = (color: string) => {
    setCustomColor(color);
    onColorSelect(color);
  };

  const handleCustomColorChange = (color: string) => {
    setCustomColor(color);
  };

  const handleCustomColorApply = () => {
    onColorSelect(customColor);
  };

  const style = position
    ? {
        position: 'fixed' as const,
        left: position.x,
        top: position.y,
        zIndex: 1000,
      }
    : {};

  return (
    <div
      className="bg-white dark:bg-slate-900 rounded-lg shadow-xl border border-gray-200 dark:border-slate-700 p-4 w-80"
      style={style}
      onClick={(e) => e.stopPropagation()}
    >
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Choose Color</h3>
        <button
          onClick={onClose}
          className="text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="space-y-4">
        {/* Preset Colors */}
        <div>
          <label className="block text-xs font-medium text-gray-600 dark:text-gray-300 mb-2">Preset Colors</label>
          <div className="grid grid-cols-6 gap-2">
            {PRESET_COLORS.map((preset) => (
              <button
                key={preset.value}
                onClick={() => handlePresetClick(preset.value)}
                className={`w-8 h-8 rounded-md border-2 transition-all hover:scale-110 ${
                  currentColor === preset.value
                    ? 'border-gray-900 dark:border-white shadow-md'
                    : 'border-gray-300 dark:border-slate-600'
                }`}
                style={{ backgroundColor: preset.value }}
                title={preset.name}
              />
            ))}
          </div>
        </div>

        {/* Custom Color */}
        <div>
          <label className="block text-xs font-medium text-gray-600 dark:text-gray-300 mb-2">Custom Color</label>
          <div className="flex gap-2 items-stretch">
            <input
              type="color"
              value={customColor}
              onChange={(e) => handleCustomColorChange(e.target.value)}
              className="w-12 h-10 border border-gray-300 dark:border-slate-600 rounded cursor-pointer flex-shrink-0"
            />
            <input
              type="text"
              value={customColor}
              onChange={(e) => handleCustomColorChange(e.target.value)}
              placeholder="#000000"
              className="flex-1 min-w-0 px-3 py-2 text-sm border border-gray-300 dark:border-slate-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-yellow-500 bg-white dark:bg-slate-800 text-gray-900 dark:text-gray-100"
            />
            <button
              onClick={handleCustomColorApply}
              className="px-4 py-2 text-sm bg-blue-500 dark:bg-yellow-500 text-white dark:text-slate-900 rounded-md hover:bg-blue-600 dark:hover:bg-yellow-600 transition-colors whitespace-nowrap flex-shrink-0"
            >
              Apply
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

ColorPickerComponent.displayName = 'ColorPicker';

export const ColorPicker = memo(ColorPickerComponent);
