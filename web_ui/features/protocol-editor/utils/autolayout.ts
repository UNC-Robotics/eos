import { type Node, type Edge, Position } from '@xyflow/react';

// Configuration for the layout
const HORIZONTAL_SPACING = 100; // Space between columns (Left to Right)
const VERTICAL_SPACING = 50; // Space between nodes in a column (Top to Bottom)
const GRID_SIZE = 20;

// Fallback dimensions in case the node hasn't rendered yet
const DEFAULT_WIDTH = 250;
const DEFAULT_HEIGHT = 150;

// Extended node type for internal calculation
type LayoutNode<T extends Record<string, unknown> = Record<string, unknown>> = Node<T> & {
  __rank?: number; // The column index (0, 1, 2...)
  __width: number; // Actual dynamic width
  __height: number; // Actual dynamic height
};

/**
 * Performs an automatic Left-to-Right hierarchical layout.
 * It calculates dynamic column widths based on the widest node in that column.
 */
export const performAutoLayout = <T extends Record<string, unknown> = Record<string, unknown>>(
  nodes: Node<T>[],
  edges: Edge[]
) => {
  // 1. Prepare Nodes with Dimensions
  // We prefer 'measured' (v12) but fall back to 'width' or defaults
  const layoutNodes: LayoutNode<T>[] = nodes.map((node) => ({
    ...node,
    __width: node.measured?.width ?? node.width ?? DEFAULT_WIDTH,
    __height: node.measured?.height ?? node.height ?? DEFAULT_HEIGHT,
  }));

  // 2. Build Graph Topology (Adjacency & In-Degree)
  const adjacency = new Map<string, string[]>(); // Parent -> Children
  const inDegree = new Map<string, number>(); // Node -> Number of incoming edges

  // Initialize maps
  layoutNodes.forEach((node) => {
    adjacency.set(node.id, []);
    inDegree.set(node.id, 0);
  });

  // Populate maps based on edges
  edges.forEach((edge) => {
    const source = adjacency.get(edge.source);
    if (source) {
      source.push(edge.target);
      inDegree.set(edge.target, (inDegree.get(edge.target) || 0) + 1);
    }
  });

  // 3. Assign Ranks (Columns) via Forward Propagation
  // Rank 0 = Roots. Rank N = Children of Rank N-1.
  const rankMap = new Map<string, number>();
  const queue: string[] = [];

  // Find root nodes (in-degree 0)
  layoutNodes.forEach((node) => {
    if ((inDegree.get(node.id) || 0) === 0) {
      queue.push(node.id);
      rankMap.set(node.id, 0);
    }
  });

  // Handle cycles/disconnected graphs: if no roots found but nodes exist, pick the first one
  if (queue.length === 0 && layoutNodes.length > 0) {
    queue.push(layoutNodes[0].id);
    rankMap.set(layoutNodes[0].id, 0);
  }

  // Process the graph to assign ranks
  while (queue.length > 0) {
    const nodeId = queue.shift()!;
    const currentRank = rankMap.get(nodeId)!;
    const children = adjacency.get(nodeId) || [];

    children.forEach((childId) => {
      const nextRank = currentRank + 1;
      const existingRank = rankMap.get(childId);

      // Push child to the right if it depends on a node in a deeper column
      // This ensures dependencies always flow Left -> Right
      if (existingRank === undefined || nextRank > existingRank) {
        rankMap.set(childId, nextRank);
        queue.push(childId);
      }
    });
  }

  // 4. Group Nodes by Rank (Column)
  const columns: LayoutNode<T>[][] = [];
  layoutNodes.forEach((node) => {
    const rank = rankMap.get(node.id) ?? 0;
    if (!columns[rank]) columns[rank] = [];
    columns[rank].push(node);
  });

  // 5. Calculate Coordinates (Left-to-Right)
  let currentX = 0;

  const finalNodes = columns.flatMap((columnNodes) => {
    if (!columnNodes || columnNodes.length === 0) return [];

    // Sort vertically within column to minimize crossings (simple ID sort for stability)
    // This keeps the layout deterministic
    columnNodes.sort((a, b) => a.id.localeCompare(b.id));

    // A. Determine Column Metrics
    let maxNodeWidth = 0;
    let totalColumnHeight = 0;

    columnNodes.forEach((node, index) => {
      maxNodeWidth = Math.max(maxNodeWidth, node.__width);
      totalColumnHeight += node.__height;

      // Add vertical spacing between nodes
      if (index < columnNodes.length - 1) {
        totalColumnHeight += VERTICAL_SPACING;
      }
    });

    // B. Determine Vertical Start Point (Center alignment)
    // We center the column vertically around Y=0
    let currentY = -(totalColumnHeight / 2);

    // C. Position Nodes
    const positionedColumn = columnNodes.map((node) => {
      // Snap coordinates to grid
      const snappedX = Math.round(currentX / GRID_SIZE) * GRID_SIZE;
      const snappedY = Math.round(currentY / GRID_SIZE) * GRID_SIZE;

      // Advance Y for the next node in this stack
      currentY += node.__height + VERTICAL_SPACING;

      // Destructure to remove internal calculation properties
      const { __rank: _rank, __width: _width, __height: _height, ...nodeWithoutInternals } = node;

      // Create new node object with updated position
      const updatedNode: Node<T> = {
        ...nodeWithoutInternals,
        position: { x: snappedX, y: snappedY },
        // Enforce Left-to-Right flow handles
        targetPosition: Position.Left,
        sourcePosition: Position.Right,
      };

      return updatedNode;
    });

    // Advance X for the next column
    // We add the width of the *widest* node in this column + spacing
    currentX += maxNodeWidth + HORIZONTAL_SPACING;

    return positionedColumn;
  });

  return { nodes: finalNodes, edges };
};
