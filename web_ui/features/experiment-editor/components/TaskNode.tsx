'use client';

import { memo, useMemo, useCallback } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import type { TaskNodeData } from '@/lib/types/experiment';
import { PORT_COLORS, BADGE_CLASSES, PORT_SIZES, adjustColorBrightness } from '@/lib/constants/theme';
import { useEditorStore } from '@/lib/stores/editorStore';

interface PortProps {
  id: string;
  name: string;
  type: string;
  position: Position;
  handleType: 'source' | 'target';
  color: string;
  bgColor: string;
  isRight?: boolean;
  hasValue?: boolean;
  hasHold?: boolean;
}

const COLORS = {
  main: PORT_COLORS.main,
  device: PORT_COLORS.device,
  resource: PORT_COLORS.resource,
  parameter: PORT_COLORS.parameter,
  badge: BADGE_CLASSES,
} as const;

const Port = memo(({ id, name, type, position, handleType, color, bgColor, isRight, hasValue, hasHold }: PortProps) => {
  const handleStyle = useMemo(
    () => ({
      position: 'absolute' as const,
      [isRight ? 'right' : 'left']: '-20px',
      top: '50%',
      transform: 'translateY(-50%)',
      width: `${PORT_SIZES.small}px`,
      height: `${PORT_SIZES.small}px`,
      background: hasValue ? color : 'white',
      border: `2px solid ${color}`,
      boxShadow: hasValue ? `0 0 4px ${color}` : 'none',
    }),
    [isRight, hasValue, color]
  );

  return (
    <div className={`relative mb-1 flex items-center gap-1 ${isRight ? 'justify-end' : ''}`}>
      <Handle type={handleType} position={position} id={id} style={handleStyle} />
      {!isRight && <div className="text-sm text-gray-700 dark:text-gray-300">{name}</div>}
      <span className={`text-xs px-1 py-0.5 ${bgColor} rounded`}>{type}</span>
      {hasHold && (
        <span
          className="text-xs px-1 py-0.5 bg-amber-100 dark:bg-amber-900/50 text-amber-700 dark:text-amber-400 rounded font-medium"
          title="Held for successor tasks"
        >
          H
        </span>
      )}
      {isRight && <div className="text-sm text-gray-700 dark:text-gray-300 text-right">{name}</div>}
    </div>
  );
});

Port.displayName = 'Port';

// Helper to check if a device/resource/parameter value is configured
const isValueConfigured = (value: unknown, type: 'device' | 'resource' | 'parameter'): boolean => {
  if (value === undefined || value === '') return false;

  if (type === 'parameter') {
    return true;
  }

  if (typeof value === 'string') {
    return value.trim() !== '';
  }

  if (typeof value === 'object' && value) {
    if ('allocation_type' in value) return true; // Dynamic allocation
    if (type === 'device' && 'lab_name' in value) {
      return (
        (value as { lab_name: string; name: string }).lab_name !== '' &&
        (value as { lab_name: string; name: string }).name !== ''
      );
    }
  }

  return false;
};

const TaskNodeComponent = ({ data, selected }: NodeProps) => {
  const { taskNode, taskSpec, isMissingSpec, onNodeClick, onNodeContextMenu } = data as TaskNodeData;
  const taskErrors = useEditorStore((state) => state.taskValidationErrors[taskNode.name]);
  const hasErrors = taskErrors && taskErrors.length > 0;

  const inputDevices = useMemo(() => Object.entries(taskSpec.input_devices || {}), [taskSpec.input_devices]);
  const outputDevices = useMemo(() => Object.entries(taskSpec.output_devices || {}), [taskSpec.output_devices]);
  const inputResources = useMemo(() => Object.entries(taskSpec.input_resources || {}), [taskSpec.input_resources]);
  const outputResources = useMemo(() => Object.entries(taskSpec.output_resources || {}), [taskSpec.output_resources]);
  const inputParams = useMemo(() => Object.entries(taskSpec.input_parameters || {}), [taskSpec.input_parameters]);
  const outputParams = useMemo(() => Object.entries(taskSpec.output_parameters || {}), [taskSpec.output_parameters]);

  // Input devices and resources should also appear as outputs (pass-through)
  // Deduplicate by name - output takes precedence over input
  const allOutputDevices = useMemo(() => {
    const result = [...outputDevices];
    inputDevices.forEach(([name, spec]) => {
      if (!result.some(([n]) => n === name)) {
        result.push([name, spec]);
      }
    });
    return result;
  }, [inputDevices, outputDevices]);

  const allOutputResources = useMemo(() => {
    const result = [...outputResources];
    inputResources.forEach(([name, spec]) => {
      if (!result.some(([n]) => n === name)) {
        result.push([name, spec]);
      }
    });
    return result;
  }, [inputResources, outputResources]);

  const headerColor = isMissingSpec ? '#d97706' : taskNode.color || '#3b82f6';
  const darkerColor = useMemo(() => adjustColorBrightness(headerColor, -10), [headerColor]);

  // Helper to render a port section
  const renderPortSection = useCallback(
    (
      items: [string, { type: string }][],
      portType: 'device' | 'resource' | 'parameter',
      direction: 'input' | 'output',
      valueSource?: Record<string, unknown>,
      holdSource?: Record<string, boolean>
    ) => {
      if (items.length === 0) return null;

      const isInput = direction === 'input';
      const portColor = COLORS[portType];
      const badgeColor = COLORS.badge[portType];

      return (
        <div className={items.length > 0 ? 'mb-3' : ''}>
          {items.map(([name, spec]) => {
            const hasValue = valueSource ? isValueConfigured(valueSource[name], portType) : undefined;

            return (
              <Port
                key={name}
                id={`${taskNode.name}-${direction}-${portType}-${name}`}
                name={name}
                type={spec.type}
                position={isInput ? Position.Left : Position.Right}
                handleType={isInput ? 'target' : 'source'}
                color={portColor}
                bgColor={badgeColor}
                isRight={!isInput}
                hasValue={hasValue}
                hasHold={holdSource?.[name]}
              />
            );
          })}
        </div>
      );
    },
    [taskNode.name]
  );

  return (
    <div
      className={`bg-white dark:bg-slate-800 rounded-lg shadow-lg border-2 transition-all duration-200 w-auto relative ${
        isMissingSpec
          ? 'border-amber-500 dark:border-amber-500 border-dashed'
          : hasErrors
            ? 'border-red-500 dark:border-red-500'
            : selected
              ? 'border-blue-500 dark:border-yellow-500 shadow-xl'
              : 'border-gray-300 dark:border-slate-600'
      }`}
      onClick={() => onNodeClick(taskNode.name)}
      onContextMenu={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onNodeContextMenu(e, taskNode.name);
      }}
    >
      {/* Validation error badge */}
      {hasErrors && (
        <div
          className="absolute -top-2 -right-2 z-10 bg-red-500 text-white text-xs font-bold rounded-full w-5 h-5 flex items-center justify-center shadow-sm"
          title={taskErrors.join('\n')}
        >
          {taskErrors.length}
        </div>
      )}
      <Handle
        type="target"
        position={Position.Left}
        id={`${taskNode.name}-main-input`}
        style={{
          top: '20px',
          width: `${PORT_SIZES.large}px`,
          height: `${PORT_SIZES.large}px`,
          background: COLORS.main.bg,
          border: `2px solid ${COLORS.main.border}`,
        }}
      />
      <Handle
        type="source"
        position={Position.Right}
        id={`${taskNode.name}-main-output`}
        style={{
          top: '20px',
          width: `${PORT_SIZES.large}px`,
          height: `${PORT_SIZES.large}px`,
          background: COLORS.main.bg,
          border: `2px solid ${COLORS.main.border}`,
        }}
      />

      {/* Header */}
      <div
        className="text-white px-3 py-1 rounded-t-md"
        style={{
          background: `linear-gradient(to right, ${headerColor}, ${darkerColor})`,
        }}
      >
        <div className="font-semibold text-base">{taskNode.name}</div>
        <div className="text-sm opacity-90">{taskSpec.type}</div>
        {isMissingSpec && (
          <div className="text-xs font-medium opacity-90 mt-0.5">⚠ Spec not found — load the package</div>
        )}
      </div>

      {/* Body */}
      <div className="px-4 py-3">
        <div className="grid grid-cols-2 gap-8">
          {/* Left Column - Inputs */}
          <div>
            {renderPortSection(inputDevices, 'device', 'input', taskNode.devices)}
            {renderPortSection(inputResources, 'resource', 'input', taskNode.resources)}
            {renderPortSection(inputParams, 'parameter', 'input', taskNode.parameters)}
          </div>

          {/* Right Column - Outputs */}
          <div>
            {renderPortSection(allOutputDevices, 'device', 'output', undefined, taskNode.device_holds)}
            {renderPortSection(allOutputResources, 'resource', 'output', undefined, taskNode.resource_holds)}
            {renderPortSection(outputParams, 'parameter', 'output')}
          </div>
        </div>
      </div>
    </div>
  );
};

TaskNodeComponent.displayName = 'TaskNode';

export const TaskNode = memo(TaskNodeComponent);
