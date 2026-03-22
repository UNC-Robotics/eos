'use client';

import { useEffect, useMemo, useCallback } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  BackgroundVariant,
  Node,
  Edge,
  useNodesState,
  useEdgesState,
  MarkerType,
  type NodeTypes,
} from '@xyflow/react';
import { useTheme } from 'next-themes';
import '@xyflow/react/dist/style.css';
import { TaskStatusNode } from './TaskStatusNode';
import { performAutoLayout } from '@/features/experiment-editor/utils/autolayout';
import { getEdgeColors } from '@/lib/constants/theme';
import type { TaskStatusInfo } from '../api/experimentDetails';
import type { ExperimentTaskConfig } from '@/lib/api/specs';

interface ExperimentFlowCanvasProps {
  experimentTasks: ExperimentTaskConfig[];
  taskStatuses: TaskStatusInfo[];
  onTaskSelect: (taskName: string | null) => void;
  selectedTaskName: string | null;
  onShowTaskList?: () => void;
}

const nodeTypes: NodeTypes = { taskStatus: TaskStatusNode };

export function ExperimentFlowCanvas({
  experimentTasks,
  taskStatuses,
  onTaskSelect,
  selectedTaskName,
  onShowTaskList,
}: ExperimentFlowCanvasProps) {
  const { resolvedTheme } = useTheme();
  const edgeColors = useMemo(() => getEdgeColors(resolvedTheme === 'dark'), [resolvedTheme]);

  const taskStatusMap = useMemo(() => {
    const map = new Map<string, TaskStatusInfo>();
    taskStatuses.forEach((task) => map.set(task.name, task));
    return map;
  }, [taskStatuses]);

  const initialNodes = useMemo((): Node[] => {
    return experimentTasks.map((expTask, index) => {
      const task = taskStatusMap.get(expTask.name);
      return {
        id: expTask.name,
        type: 'taskStatus',
        position: { x: 0, y: index * 100 },
        data: {
          name: expTask.name,
          type: expTask.type,
          status: task?.status || 'CREATED',
        },
      };
    });
  }, [experimentTasks, taskStatusMap]);

  const initialEdges = useMemo((): Edge[] => {
    const edges: Edge[] = [];
    experimentTasks.forEach((expTask) => {
      if (expTask.dependencies && expTask.dependencies.length > 0) {
        expTask.dependencies.forEach((dep) => {
          edges.push({
            id: `${dep}-${expTask.name}`,
            source: dep,
            target: expTask.name,
            type: 'smoothstep',
            style: {
              stroke: edgeColors.dependency,
              strokeWidth: 2,
            },
            markerEnd: {
              type: MarkerType.ArrowClosed,
              color: edgeColors.dependency,
              width: 20,
              height: 20,
            },
            animated: false,
          });
        });
      }
    });
    return edges;
  }, [experimentTasks, edgeColors]);

  const { nodes: layoutedNodes, edges: layoutedEdges } = useMemo(
    () => performAutoLayout(initialNodes, initialEdges),
    [initialNodes, initialEdges]
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(layoutedNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(layoutedEdges);

  useEffect(() => {
    setNodes((currentNodes) =>
      currentNodes.map((node) => {
        const task = taskStatusMap.get(node.id);
        if (task && node.data.status !== task.status) {
          return { ...node, data: { ...node.data, status: task.status } };
        }
        return node;
      })
    );
  }, [taskStatusMap, setNodes]);

  useEffect(() => {
    setEdges((currentEdges) =>
      currentEdges.map((edge) => ({
        ...edge,
        style: { ...edge.style, stroke: edgeColors.dependency, strokeWidth: 2 },
        markerEnd: { type: MarkerType.ArrowClosed, color: edgeColors.dependency, width: 20, height: 20 },
      }))
    );
  }, [edgeColors, setEdges]);

  useEffect(() => {
    setNodes((currentNodes) => currentNodes.map((node) => ({ ...node, selected: node.id === selectedTaskName })));
  }, [selectedTaskName, setNodes]);

  const onNodeClick = useCallback((_event: React.MouseEvent, node: Node) => onTaskSelect(node.id), [onTaskSelect]);
  const onPaneClick = useCallback(() => onTaskSelect(null), [onTaskSelect]);

  if (experimentTasks.length === 0) {
    return (
      <div className="w-full h-full flex items-center justify-center bg-gray-50 dark:bg-slate-800">
        <div className="text-center">
          <p className="text-base text-gray-500 dark:text-gray-400">
            Experiment definition is required to show experiment DAG.
          </p>
          {onShowTaskList && (
            <button
              onClick={onShowTaskList}
              className="mt-3 text-sm font-medium text-blue-600 dark:text-blue-400 hover:underline"
            >
              View task list
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="w-full h-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        onPaneClick={onPaneClick}
        nodeTypes={nodeTypes}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={true}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.1}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1.5} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
