'use client';

import { useCallback, useState, useEffect, useRef, useMemo } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  type Node,
  type Edge,
  type Connection,
  type NodeTypes,
  type NodeChange,
  addEdge,
  useNodesState,
  useEdgesState,
  useReactFlow,
  BackgroundVariant,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Panel, Group, Separator } from 'react-resizable-panels';
import { useTheme } from 'next-themes';
import { TaskNode } from './TaskNode';
import { Toolbar } from './Toolbar';
import { ContextMenu } from './ContextMenu';
import { NewTaskModal } from './NewTaskModal';
import { TaskPropertiesPanel } from './TaskPropertiesPanel';
import { ColorPicker } from './ColorPicker';
import { ExportImageDialog } from './ExportImageDialog';
import { ConfirmDialog } from '@/components/dialogs/ConfirmDialog';
import { ToastContainer } from '@/components/ui/Toast';
import { useToast } from '@/components/ui/useToast';
import { OptimizerEditorPanel } from './OptimizerEditorPanel';
import { ValidationErrorsPanel } from './ValidationErrorsPanel';
import { useEditorStore } from '@/lib/stores/editorStore';
import { useExperimentValidation } from '@/hooks/useExperimentValidation';
import type { TaskSpec, TaskNodeData, TaskNode as TaskNodeType } from '@/lib/types/experiment';
import { EDITOR_LAYOUT, getEdgeColors } from '@/lib/constants/theme';
import { performAutoLayout } from '../utils/autolayout';
import { resolveOverlaps } from '../utils/preventOverlaps';

const nodeTypes: NodeTypes = { taskNode: TaskNode };
const GRID_SIZE = EDITOR_LAYOUT.gridSize;

// Helper functions extracted outside component for performance
const createEdge = (
  source: string,
  target: string,
  sourceHandle: string,
  targetHandle: string,
  style?: React.CSSProperties
): Edge => ({
  id: `${source}-${target}-${sourceHandle}-${targetHandle}`,
  source,
  target,
  sourceHandle,
  targetHandle,
  type: 'default',
  ...(style && { style }),
});

const parseTaskRef = (value: unknown): [string, string] | null => {
  if (typeof value === 'string' && value.includes('.')) {
    const [taskId, param] = value.split('.');
    return [taskId, param];
  }
  return null;
};

const snapToGrid = (pos: { x: number; y: number }): { x: number; y: number } => ({
  x: Math.round(pos.x / GRID_SIZE) * GRID_SIZE,
  y: Math.round(pos.y / GRID_SIZE) * GRID_SIZE,
});

// Connection type helpers
const isMainDependencyConnection = (sourceHandle: string, targetHandle: string): boolean =>
  sourceHandle.includes('main-output') && targetHandle.includes('main-input');

const isDeviceConnection = (sourceHandle: string, targetHandle: string): boolean =>
  sourceHandle.includes('-output-device-') && targetHandle.includes('-input-device-');

const isResourceConnection = (sourceHandle: string, targetHandle: string): boolean =>
  sourceHandle.includes('-output-resource-') && targetHandle.includes('-input-resource-');

const isParameterConnection = (sourceHandle: string, targetHandle: string): boolean =>
  sourceHandle.includes('-output-parameter-') && targetHandle.includes('-input-parameter-');

export function ExperimentEditor() {
  const { resolvedTheme } = useTheme();
  // Manual validation — triggered by the Validate button
  const { validate } = useExperimentValidation();

  const tasks = useEditorStore((state) => state.tasks);
  const taskTemplates = useEditorStore((state) => state.taskTemplates);
  const labSpecs = useEditorStore((state) => state.labSpecs);
  const labs = useEditorStore((state) => state.labs);
  const selectedNodeName = useEditorStore((state) => state.selectedNodeName);
  const isPropertiesPanelOpen = useEditorStore((state) => state.isPropertiesPanelOpen);
  const clipboard = useEditorStore((state) => state.clipboard);
  const addTask = useEditorStore((state) => state.addTask);
  const updateTask = useEditorStore((state) => state.updateTask);
  const deleteTask = useEditorStore((state) => state.deleteTask);
  const copyNodes = useEditorStore((state) => state.copyNodes);
  const pasteNodes = useEditorStore((state) => state.pasteNodes);
  const setIsPropertiesPanelOpen = useEditorStore((state) => state.setIsPropertiesPanelOpen);
  const getNextTaskName = useEditorStore((state) => state.getNextTaskName);
  const batchOperation = useEditorStore((state) => state.batchOperation);
  const needsOverlapResolution = useEditorStore((state) => state.needsOverlapResolution);
  const storedViewport = useEditorStore((state) => state.viewport);
  const setStoredViewport = useEditorStore((state) => state.setViewport);

  // Edge colors that adapt to theme - memoized to prevent infinite loops
  const edgeColors = useMemo(() => getEdgeColors(resolvedTheme === 'dark'), [resolvedTheme]);

  const { screenToFlowPosition, getViewport } = useReactFlow();
  const [nodes, setNodes, applyNodesChange] = useNodesState<Node<TaskNodeData>>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [contextMenu, setContextMenu] = useState<{
    position: { x: number; y: number };
    nodeId: string | null;
    edgeId: string | null;
  } | null>(null);
  const [isNewTaskModalOpen, setIsNewTaskModalOpen] = useState(false);
  const [isExportDialogOpen, setIsExportDialogOpen] = useState(false);
  const [newNodePosition, setNewNodePosition] = useState({ x: 0, y: 0 });
  const [colorPickerState, setColorPickerState] = useState<{
    nodeId: string;
    position: { x: number; y: number };
  } | null>(null);
  const [confirmDialog, setConfirmDialog] = useState<{
    title: string;
    message: string;
    onConfirm: () => void;
  } | null>(null);
  const { toasts, showToast, closeToast } = useToast();
  const [selectedNodes, setSelectedNodes] = useState<string[]>([]);
  const mousePositionRef = useRef({ x: 0, y: 0 });

  // Save viewport to store on unmount so it survives navigation
  const getViewportRef = useRef(getViewport);
  getViewportRef.current = getViewport;
  useEffect(() => {
    return () => {
      setStoredViewport(getViewportRef.current());
    };
  }, [setStoredViewport]);

  // Stable callback refs that don't change
  const onNodeClickRef = useRef((nodeName: string) => {
    useEditorStore.getState().setSelectedNodeName(nodeName);
  });

  const onNodeContextMenuRef = useRef((event: React.MouseEvent, nodeName: string) => {
    event.preventDefault();
    event.stopPropagation();

    setContextMenu({
      position: { x: event.clientX, y: event.clientY },
      nodeId: nodeName,
      edgeId: null,
    });
  });

  // Memoize task lookup map for performance
  const taskMap = useMemo(() => new Map(tasks.map((t) => [t.name, t])), [tasks]);
  const templateMap = useMemo(() => new Map(taskTemplates.map((t) => [t.type, t])), [taskTemplates]);

  // Sync nodes
  useEffect(() => {
    const missingTemplates = new Set<string>();
    const validNodes = tasks.map((task) => {
      const taskSpec = templateMap.get(task.type);
      const isMissingSpec = !taskSpec;
      if (isMissingSpec) {
        missingTemplates.add(task.type);
      }
      return {
        id: task.name,
        type: 'taskNode',
        position: task.position,
        data: {
          taskNode: task,
          taskSpec: taskSpec ?? ({ type: task.type, desc: '', device_types: [] } as TaskSpec),
          isMissingSpec,
          onNodeClick: onNodeClickRef.current,
          onNodeContextMenu: onNodeContextMenuRef.current,
        },
      };
    });

    // Show toast if any templates are missing
    if (missingTemplates.size > 0) {
      showToast(
        'error',
        'Missing Task Specs',
        `The following task types are not in the database (package may not be loaded): ${Array.from(missingTemplates).join(', ')}`
      );
    }

    setNodes(validNodes);

    // Transfer pending overlap resolution request now that nodes are synced.
    // Both setNodes and setState are batched by React 18, so the overlap
    // resolution effect will see the new nodes + the active flag together.
    if (useEditorStore.getState().overlapResolutionRequested) {
      useEditorStore.setState({
        overlapResolutionRequested: false,
        needsOverlapResolution: true,
      });
    }
  }, [tasks, templateMap, setNodes, showToast]);

  // Sync edges - create edges from task dependencies and references
  useEffect(() => {
    const flowEdges: Edge[] = [];

    const addReferenceEdges = (
      task: TaskNodeType,
      assignments: Record<string, unknown> | undefined,
      portType: 'device' | 'resource' | 'parameter',
      color: string
    ) => {
      Object.entries(assignments || {}).forEach(([name, value]) => {
        const ref = parseTaskRef(value);
        if (ref && taskMap.has(ref[0])) {
          flowEdges.push(
            createEdge(
              ref[0],
              task.name,
              `${ref[0]}-output-${portType}-${ref[1]}`,
              `${task.name}-input-${portType}-${name}`,
              { stroke: color }
            )
          );
        }
      });
    };

    tasks.forEach((task) => {
      // Dependency edges
      task.dependencies?.forEach((depName) => {
        flowEdges.push(
          createEdge(depName, task.name, `${depName}-main-output`, `${task.name}-main-input`, {
            strokeWidth: 4,
            stroke: edgeColors.dependency,
          })
        );
      });

      // Device, Resource, and Parameter edges
      addReferenceEdges(task, task.devices, 'device', edgeColors.device);
      addReferenceEdges(task, task.resources, 'resource', edgeColors.resource);
      addReferenceEdges(task, task.parameters, 'parameter', edgeColors.parameter);
    });

    setEdges(flowEdges);
  }, [tasks, taskMap, setEdges, edgeColors]);

  // Post-render overlap resolution: after AI updates, wait for React Flow to measure
  // nodes, then resolve any overlaps using actual dimensions
  useEffect(() => {
    if (!needsOverlapResolution || nodes.length < 2) return;

    const allMeasured = nodes.every((n) => n.measured?.width && n.measured?.height);
    if (!allMeasured) return;

    const resolved = resolveOverlaps(nodes);
    useEditorStore.setState({ needsOverlapResolution: false });
    if (!resolved) return;

    setNodes(resolved);
    batchOperation(() => {
      resolved.forEach((node) => {
        updateTask(node.id, { position: node.position });
      });
    });
  }, [nodes, needsOverlapResolution, setNodes, batchOperation, updateTask]);

  // Handle device/resource/parameter port connections
  const handlePortConnection = useCallback(
    (
      connection: Connection,
      sourceHandle: string,
      targetHandle: string,
      field: 'devices' | 'resources' | 'parameters',
      portType: string,
      edgeColor: string
    ) => {
      const sourceTask = taskMap.get(connection.source!);
      const targetTask = taskMap.get(connection.target!);
      if (!sourceTask || !targetTask) return;

      const sourceSpec = templateMap.get(sourceTask.type);
      const targetSpec = templateMap.get(targetTask.type);
      if (!sourceSpec || !targetSpec) return;

      // Parse handle IDs to extract parameter names
      const sourceParam = sourceHandle.split(`-output-${portType}-`)[1];
      const targetParam = targetHandle.split(`-input-${portType}-`)[1];

      if (!sourceParam || !targetParam) {
        console.error('Failed to parse port names', { sourceHandle, targetHandle, sourceParam, targetParam });
        return;
      }

      // Determine source and target types based on field
      let sourceType: string | undefined;
      let targetType: string | undefined;

      if (field === 'devices') {
        sourceType = sourceSpec.output_devices?.[sourceParam]?.type || sourceSpec.input_devices?.[sourceParam]?.type;
        targetType = targetSpec.input_devices?.[targetParam]?.type;
      } else if (field === 'resources') {
        sourceType =
          sourceSpec.output_resources?.[sourceParam]?.type || sourceSpec.input_resources?.[sourceParam]?.type;
        targetType = targetSpec.input_resources?.[targetParam]?.type;
      } else {
        sourceType = sourceSpec.output_parameters?.[sourceParam]?.type;
        targetType = targetSpec.input_parameters?.[targetParam]?.type;
      }

      // Validate types match
      if (sourceType !== targetType) {
        showToast(
          'error',
          'Connection Error',
          `Cannot connect: Type mismatch! Source: ${sourceType}, Target: ${targetType}`
        );
        return;
      }

      // Update task with reference
      updateTask(connection.target!, {
        [field]: { ...targetTask[field], [targetParam]: `${connection.source}.${sourceParam}` },
      });

      // Add edge with appropriate color
      setEdges((eds) => addEdge({ ...connection, style: { stroke: edgeColor } }, eds));
    },
    [taskMap, templateMap, updateTask, setEdges, showToast]
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      if (!connection.source || !connection.target) return;

      const sourceHandle = connection.sourceHandle || '';
      const targetHandle = connection.targetHandle || '';

      // Main dependency connection
      if (isMainDependencyConnection(sourceHandle, targetHandle)) {
        const targetTask = taskMap.get(connection.target);
        if (targetTask && !targetTask.dependencies?.includes(connection.source)) {
          updateTask(connection.target, { dependencies: [...(targetTask.dependencies || []), connection.source] });
        }
        setEdges((eds) => addEdge({ ...connection, style: { strokeWidth: 4, stroke: edgeColors.dependency } }, eds));
        return;
      }

      // Device/Resource/Parameter connections
      if (isDeviceConnection(sourceHandle, targetHandle)) {
        handlePortConnection(connection, sourceHandle, targetHandle, 'devices', 'device', edgeColors.device);
        return;
      }

      if (isResourceConnection(sourceHandle, targetHandle)) {
        handlePortConnection(connection, sourceHandle, targetHandle, 'resources', 'resource', edgeColors.resource);
        return;
      }

      if (isParameterConnection(sourceHandle, targetHandle)) {
        handlePortConnection(connection, sourceHandle, targetHandle, 'parameters', 'parameter', edgeColors.parameter);
        return;
      }

      // Mixed types - not allowed
      if (sourceHandle.includes('output-') && targetHandle.includes('input-')) {
        const getPortType = (handle: string) =>
          handle.includes('-device-') ? 'device' : handle.includes('-resource-') ? 'resource' : 'parameter';
        const sourcePortType = getPortType(sourceHandle);
        const targetPortType = getPortType(targetHandle);
        showToast(
          'error',
          'Connection Error',
          `Cannot connect: ${sourcePortType}s can only connect to ${sourcePortType}s (not ${targetPortType}s)`
        );
        return;
      }

      setEdges((eds) => addEdge(connection, eds));
    },
    [taskMap, updateTask, setEdges, edgeColors, handlePortConnection, showToast]
  );

  const handleContextMenu = useCallback(
    (event: React.MouseEvent | MouseEvent, item?: Node | Edge) => {
      event.preventDefault();
      const isEdge = item && 'source' in item;

      // If we clicked on a node that's part of a multi-selection, show multi-select menu
      if (!isEdge && item && selectedNodes.length > 1 && selectedNodes.includes(item.id)) {
        setContextMenu({
          position: { x: event.clientX, y: event.clientY },
          nodeId: item.id,
          edgeId: null,
        });
        return;
      }

      // If nodes are selected and we're right-clicking on pane, show node context menu
      if (selectedNodes.length > 0 && !item) {
        setContextMenu({
          position: { x: event.clientX, y: event.clientY },
          nodeId: selectedNodes[0], // Use first selected node as reference
          edgeId: null,
        });
        return;
      }

      setContextMenu({
        position: { x: event.clientX, y: event.clientY },
        nodeId: item && !isEdge ? item.id : null,
        edgeId: isEdge ? (item as Edge).id : null,
      });
    },
    [selectedNodes]
  );

  const handleNewTask = useCallback(() => {
    setNewNodePosition(contextMenu?.position || { x: 0, y: 0 });
    setIsNewTaskModalOpen(true);
  }, [contextMenu]);

  const handleDeleteEdge = useCallback(() => {
    if (!contextMenu?.edgeId) return;

    const edge = edges.find((e) => e.id === contextMenu.edgeId);
    if (!edge) return;

    const targetHandle = edge.targetHandle || '';
    const targetTask = taskMap.get(edge.target);
    if (!targetTask) return;

    // Delete main dependency
    if (targetHandle.includes('main-input')) {
      updateTask(edge.target, { dependencies: targetTask.dependencies?.filter((d) => d !== edge.source) || [] });
      return;
    }

    // Delete device, resource, or parameter
    let targetParam: string;
    let field: 'devices' | 'resources' | 'parameters';

    if (targetHandle.includes('-input-device-')) {
      targetParam = targetHandle.split('-input-device-')[1];
      field = 'devices';
    } else if (targetHandle.includes('-input-resource-')) {
      targetParam = targetHandle.split('-input-resource-')[1];
      field = 'resources';
    } else if (targetHandle.includes('-input-parameter-')) {
      targetParam = targetHandle.split('-input-parameter-')[1];
      field = 'parameters';
    } else {
      return;
    }

    if (!targetParam) return;

    const updated = { ...(targetTask[field] || {}) } as Record<string, string | number>;
    delete updated[targetParam];
    updateTask(edge.target, { [field]: updated });
  }, [contextMenu, edges, taskMap, updateTask]);

  const handleSetColor = useCallback(() => {
    if (contextMenu?.nodeId && contextMenu?.position) {
      setColorPickerState({
        nodeId: contextMenu.nodeId,
        position: contextMenu.position,
      });
      setContextMenu(null);
    }
  }, [contextMenu]);

  const handleSelectTemplate = useCallback(
    (template: TaskSpec) => {
      const position = snapToGrid(screenToFlowPosition(newNodePosition));
      addTask({
        name: getNextTaskName(),
        type: template.type,
        position,
        devices: {},
        resources: {},
        parameters: {},
      });
    },
    [newNodePosition, addTask, screenToFlowPosition, getNextTaskName]
  );

  const handleNodesChange = useCallback(
    (changes: NodeChange<Node<TaskNodeData>>[]) => {
      applyNodesChange(changes);

      changes.forEach((change) => {
        if (
          change.type === 'position' &&
          change.position &&
          (change.dragging === false || change.dragging === undefined)
        ) {
          updateTask(change.id, { position: snapToGrid(change.position) });
        }
      });
    },
    [applyNodesChange, updateTask]
  );

  // Track selected nodes from React Flow
  const handleSelectionChange = useCallback(({ nodes }: { nodes: Node[] }) => {
    setSelectedNodes(nodes.map((n) => n.id));
  }, []);

  // Track mouse position for paste
  const handleMouseMove = useCallback((event: React.MouseEvent) => {
    mousePositionRef.current = { x: event.clientX, y: event.clientY };
  }, []);

  // Copy handler
  const handleCopy = useCallback(() => {
    const nodesToCopy = selectedNodes.length > 0 ? selectedNodes : contextMenu?.nodeId ? [contextMenu.nodeId] : [];
    if (nodesToCopy.length === 0) return;

    copyNodes(nodesToCopy);
    showToast('success', 'Copied', `Copied ${nodesToCopy.length} task${nodesToCopy.length > 1 ? 's' : ''}`);
  }, [selectedNodes, contextMenu, copyNodes, showToast]);

  // Paste handler
  const handlePaste = useCallback(() => {
    if (clipboard.length === 0) return;

    const flowPosition = screenToFlowPosition(mousePositionRef.current);
    const pastedNodeIds = pasteNodes(flowPosition);
    showToast('success', 'Pasted', `Pasted ${pastedNodeIds.length} task${pastedNodeIds.length > 1 ? 's' : ''}`);
  }, [clipboard, screenToFlowPosition, pasteNodes, showToast]);

  // Update delete to handle multiple selected nodes
  const handleDelete = useCallback(() => {
    const nodesToDelete = selectedNodes.length > 0 ? selectedNodes : contextMenu?.nodeId ? [contextMenu.nodeId] : [];
    if (nodesToDelete.length === 0) return;

    // Use batchOperation for multiple deletes to group into single undo operation
    if (nodesToDelete.length > 1) {
      batchOperation(() => {
        nodesToDelete.forEach((nodeId) => deleteTask(nodeId));
      });
    } else {
      // Single delete doesn't need batch
      deleteTask(nodesToDelete[0]);
    }
  }, [selectedNodes, contextMenu, deleteTask, batchOperation]);

  // Global context menu handler for multi-select
  useEffect(() => {
    const handleGlobalContextMenu = (event: MouseEvent) => {
      const target = event.target as HTMLElement;
      const isInReactFlow = target.closest('.react-flow');

      if (isInReactFlow && selectedNodes.length > 0) {
        const isNode = target.closest('.react-flow__node');
        const isEdge = target.closest('.react-flow__edge');

        if (!isNode && !isEdge) {
          // Clicking on the selection box or pane - show multi-select menu
          event.preventDefault();
          event.stopPropagation();
          setContextMenu({
            position: { x: event.clientX, y: event.clientY },
            nodeId: selectedNodes[0],
            edgeId: null,
          });
        }
      }
    };

    document.addEventListener('contextmenu', handleGlobalContextMenu);
    return () => document.removeEventListener('contextmenu', handleGlobalContextMenu);
  }, [selectedNodes]);

  // Keyboard shortcuts
  useEffect(() => {
    const undo = useEditorStore.getState().undo;
    const redo = useEditorStore.getState().redo;

    const handleKeyDown = (event: KeyboardEvent) => {
      // Check if user is typing in an input field
      const target = event.target as HTMLElement;
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') return;

      // Undo: Ctrl+Z (Windows/Linux) or Cmd+Z (Mac)
      if ((event.metaKey || event.ctrlKey) && event.key === 'z' && !event.shiftKey) {
        event.preventDefault();
        undo();
        return;
      }

      // Redo: Ctrl+Shift+Z or Ctrl+Y (Windows/Linux) or Cmd+Shift+Z (Mac)
      if ((event.metaKey || event.ctrlKey) && ((event.shiftKey && event.key === 'z') || event.key === 'y')) {
        event.preventDefault();
        redo();
        return;
      }

      if ((event.metaKey || event.ctrlKey) && event.key === 'c') {
        event.preventDefault();
        handleCopy();
      }

      if ((event.metaKey || event.ctrlKey) && event.key === 'v') {
        event.preventDefault();
        handlePaste();
      }

      // Delete: Delete or Backspace key
      if (event.key === 'Delete' || event.key === 'Backspace') {
        event.preventDefault();
        handleDelete();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleCopy, handlePaste, handleDelete]);

  // Auto Layout Handler
  const handleAutoLayout = useCallback(() => {
    // Show confirmation dialog before applying layout
    setConfirmDialog({
      title: 'Apply Auto Layout?',
      message: 'This will automatically arrange all nodes in a left-to-right hierarchical layout.',
      onConfirm: () => {
        // Calculate new layout using auto-layout utility
        const { nodes: newNodes, edges: newEdges } = performAutoLayout(nodes, edges);

        // Update React Flow State
        setNodes(newNodes);
        setEdges(newEdges);

        // Use batchOperation to group all position updates into single undo operation
        batchOperation(() => {
          newNodes.forEach((node) => {
            updateTask(node.id, { position: node.position });
          });
        });

        showToast('success', 'Layout Applied', 'Nodes have been auto-arranged left-to-right.');
        setConfirmDialog(null);
      },
    });
  }, [nodes, edges, setNodes, setEdges, updateTask, batchOperation, showToast]);

  const selectedTask = useMemo(() => taskMap.get(selectedNodeName || ''), [taskMap, selectedNodeName]);
  const selectedTaskSpec = useMemo(
    () =>
      selectedTask
        ? (templateMap.get(selectedTask.type) ?? ({ type: selectedTask.type, desc: '', device_types: [] } as TaskSpec))
        : null,
    [selectedTask, templateMap]
  );
  const isSelectedTaskMissingSpec = useMemo(
    () => (selectedTask ? !templateMap.has(selectedTask.type) : false),
    [selectedTask, templateMap]
  );

  const isOptimizerPanelOpen = useEditorStore((state) => state.isOptimizerPanelOpen);
  const setSelectedNodeName = useEditorStore((state) => state.setSelectedNodeName);

  const handleSelectTaskFromError = useCallback(
    (taskName: string) => {
      setSelectedNodeName(taskName);
    },
    [setSelectedNodeName]
  );

  // Calculate default sizes based on what's open (must add up to 100%)
  const getCanvasSize = () => {
    const sidePanels = [isOptimizerPanelOpen, isPropertiesPanelOpen && selectedTask].filter(
      Boolean
    ).length;
    if (sidePanels === 2) return '45%';
    if (isOptimizerPanelOpen) return '70%';
    if (isPropertiesPanelOpen) return '78%';
    return '100%';
  };

  const getTaskPropertiesSize = () => {
    return '22%';
  };

  return (
    <div className="h-full flex flex-col">
      <Toolbar
        labSpecs={labSpecs}
        onAutoLayout={handleAutoLayout}
        onExportImage={() => setIsExportDialogOpen(true)}
        onValidate={validate}
      />

      <Group orientation="horizontal" className="flex-1">
        {/* Main Canvas Panel */}
        <Panel id="canvas-panel" defaultSize={getCanvasSize()} minSize="30%">
          <div className="h-full flex flex-col">
            <div className="flex-1 relative bg-gray-50 dark:bg-slate-950">
              <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={handleNodesChange}
                onEdgesChange={onEdgesChange}
                onConnect={onConnect}
                onSelectionChange={handleSelectionChange}
                onPaneContextMenu={(e) => handleContextMenu(e)}
                onNodeContextMenu={(e, node) => handleContextMenu(e, node)}
                onEdgeContextMenu={(e, edge) => handleContextMenu(e, edge)}
                onMouseMove={handleMouseMove}
                nodeTypes={nodeTypes}
                selectionOnDrag
                snapToGrid
                snapGrid={[GRID_SIZE, GRID_SIZE]}
                autoPanOnNodeDrag={false}
                autoPanOnConnect={false}
                onlyRenderVisibleElements
                elevateNodesOnSelect={false}
                zoomOnDoubleClick={false}
                minZoom={0.1}
                defaultViewport={storedViewport}
                proOptions={{ hideAttribution: true }}
              >
                <Background variant={BackgroundVariant.Dots} gap={GRID_SIZE} size={1.5} />
                <Controls />
              </ReactFlow>

              <ContextMenu
                position={contextMenu?.position || null}
                nodeId={contextMenu?.nodeId || null}
                edgeId={contextMenu?.edgeId || null}
                selectedNodeCount={selectedNodes.length || (contextMenu?.nodeId ? 1 : 0)}
                hasClipboard={clipboard.length > 0}
                onNewTask={handleNewTask}
                onDeleteTask={handleDelete}
                onDeleteEdge={handleDeleteEdge}
                onSetColor={handleSetColor}
                onCopy={handleCopy}
                onPaste={handlePaste}
                onClose={() => setContextMenu(null)}
              />

              {colorPickerState && (
                <ColorPicker
                  currentColor={taskMap.get(colorPickerState.nodeId)?.color}
                  position={colorPickerState.position}
                  onColorSelect={(color) => {
                    updateTask(colorPickerState.nodeId, { color });
                    setColorPickerState(null);
                  }}
                  onClose={() => setColorPickerState(null)}
                />
              )}

              <NewTaskModal
                isOpen={isNewTaskModalOpen}
                onClose={() => setIsNewTaskModalOpen(false)}
                templates={taskTemplates}
                onSelectTemplate={handleSelectTemplate}
              />

              {confirmDialog && (
                <ConfirmDialog
                  isOpen={!!confirmDialog}
                  onClose={() => setConfirmDialog(null)}
                  onConfirm={confirmDialog.onConfirm}
                  title={confirmDialog.title}
                  message={confirmDialog.message}
                />
              )}

              <ExportImageDialog isOpen={isExportDialogOpen} onClose={() => setIsExportDialogOpen(false)} />

              <ToastContainer toasts={toasts} onClose={closeToast} />
            </div>
            <ValidationErrorsPanel onSelectTask={handleSelectTaskFromError} />
          </div>
        </Panel>

        {/* Resize Handle - Only show when task properties panel is open AND a task is selected */}
        {isPropertiesPanelOpen && selectedTask && (
          <>
            <Separator className="w-1 bg-gray-200 dark:bg-gray-700 hover:bg-blue-500 dark:hover:bg-yellow-500 transition-colors" />

            {/* Task Properties Panel */}
            <Panel id="task-properties-panel" defaultSize={getTaskPropertiesSize()} minSize="20%" maxSize="40%">
              <TaskPropertiesPanel
                isOpen={isPropertiesPanelOpen}
                taskNode={selectedTask}
                taskSpec={selectedTaskSpec || null}
                isMissingSpec={isSelectedTaskMissingSpec}
                labSpecs={labSpecs}
                selectedLabs={labs}
                onClose={() => setIsPropertiesPanelOpen(false)}
                onUpdate={updateTask}
              />
            </Panel>
          </>
        )}

        {/* Resize Handle - Only show when optimizer panel is open */}
        {isOptimizerPanelOpen && (
          <>
            <Separator className="w-1 bg-gray-200 dark:bg-gray-700 hover:bg-blue-500 dark:hover:bg-yellow-500 transition-colors" />

            {/* Optimizer Panel */}
            <Panel id="optimizer-panel" defaultSize="30%" minSize="20%" maxSize="50%">
              <OptimizerEditorPanel />
            </Panel>
          </>
        )}

      </Group>
    </div>
  );
}
