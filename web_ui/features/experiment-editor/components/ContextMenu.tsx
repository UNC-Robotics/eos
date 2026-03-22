'use client';

import { memo } from 'react';
import { Plus, Trash2, Palette, Copy, Clipboard, type LucideIcon } from 'lucide-react';

interface ContextMenuProps {
  position: { x: number; y: number } | null;
  nodeId: string | null;
  edgeId: string | null;
  selectedNodeCount: number;
  hasClipboard: boolean;
  onNewTask: () => void;
  onDeleteTask: () => void;
  onDeleteEdge: () => void;
  onSetColor: () => void;
  onCopy: () => void;
  onPaste: () => void;
  onClose: () => void;
}

interface MenuItemProps {
  icon: LucideIcon;
  label: string;
  onClick: () => void;
  variant?: 'default' | 'danger';
}

const MenuItem = memo(({ icon: Icon, label, onClick, variant = 'default' }: MenuItemProps) => {
  const variantClasses =
    variant === 'danger'
      ? 'hover:bg-red-50 dark:hover:bg-red-900/30 text-red-600 dark:text-red-400'
      : 'hover:bg-gray-100 dark:hover:bg-slate-700 text-gray-900 dark:text-gray-100';

  return (
    <button
      onClick={onClick}
      className={`w-full px-4 py-2 text-sm text-left flex items-center gap-2 transition-colors ${variantClasses}`}
    >
      <Icon className="w-4 h-4" />
      <span>{label}</span>
    </button>
  );
});

MenuItem.displayName = 'MenuItem';

const ContextMenuComponent = ({
  position,
  nodeId,
  edgeId,
  selectedNodeCount,
  hasClipboard,
  onNewTask,
  onDeleteTask,
  onDeleteEdge,
  onSetColor,
  onCopy,
  onPaste,
  onClose,
}: ContextMenuProps) => {
  if (!position) return null;

  const getMenuItems = () => {
    if (edgeId) {
      return [
        <MenuItem
          key="delete-edge"
          icon={Trash2}
          label="Delete Edge"
          onClick={() => {
            onDeleteEdge();
            onClose();
          }}
          variant="danger"
        />,
      ];
    }
    if (nodeId) {
      const copyLabel = selectedNodeCount > 1 ? `Copy ${selectedNodeCount} Tasks` : 'Copy Task';
      const deleteLabel = selectedNodeCount > 1 ? `Delete ${selectedNodeCount} Tasks` : 'Delete Task';

      return [
        <MenuItem
          key="copy"
          icon={Copy}
          label={copyLabel}
          onClick={() => {
            onCopy();
            onClose();
          }}
        />,
        ...(hasClipboard
          ? [
              <MenuItem
                key="paste"
                icon={Clipboard}
                label="Paste"
                onClick={() => {
                  onPaste();
                  onClose();
                }}
              />,
            ]
          : []),
        <MenuItem
          key="set-color"
          icon={Palette}
          label="Set Color"
          onClick={() => {
            onSetColor();
            onClose();
          }}
        />,
        <MenuItem
          key="delete-task"
          icon={Trash2}
          label={deleteLabel}
          onClick={() => {
            onDeleteTask();
            onClose();
          }}
          variant="danger"
        />,
      ];
    }
    return [
      <MenuItem
        key="new-task"
        icon={Plus}
        label="New Task"
        onClick={() => {
          onNewTask();
          onClose();
        }}
      />,
      ...(hasClipboard
        ? [
            <MenuItem
              key="paste"
              icon={Clipboard}
              label="Paste"
              onClick={() => {
                onPaste();
                onClose();
              }}
            />,
          ]
        : []),
    ];
  };

  return (
    <>
      {/* Backdrop to close menu on click outside */}
      <div
        className="fixed inset-0 z-40"
        onClick={onClose}
        onContextMenu={(e) => {
          e.preventDefault();
          onClose();
        }}
      />

      {/* Context menu */}
      <div
        className="fixed bg-white dark:bg-slate-900 rounded-lg shadow-xl border border-gray-200 dark:border-slate-700 py-1 z-50"
        style={{ left: position.x, top: position.y }}
      >
        {getMenuItems()}
      </div>
    </>
  );
};

ContextMenuComponent.displayName = 'ContextMenu';

export const ContextMenu = memo(ContextMenuComponent);
