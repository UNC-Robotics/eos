export interface ParameterSpec {
  type: 'int' | 'float' | 'str' | 'bool' | 'choice' | 'list' | 'dict';
  desc?: string;
  value?: unknown;

  // Numeric types (int, float)
  unit?: string;
  min?: number | number[]; // number for numeric types, number[] for list element bounds
  max?: number | number[]; // number for numeric types, number[] for list element bounds

  // Choice type
  choices?: string[];

  // List type
  element_type?: string;
  length?: number;
}

export interface ParameterValue {
  mode: 'static' | 'reference';
  value: unknown;
}

export interface DeviceSpec {
  type: string;
  desc: string;
}

export interface ResourceSpec {
  type: string;
  desc: string;
}

export interface TaskSpec {
  type: string;
  desc: string;
  device_types: string[];
  packageName?: string;
  input_devices?: Record<string, DeviceSpec>;
  output_devices?: Record<string, DeviceSpec>;
  input_resources?: Record<string, ResourceSpec>;
  output_resources?: Record<string, ResourceSpec>;
  input_parameters?: Record<string, ParameterSpec>;
  output_parameters?: Record<string, ParameterSpec>;
}

// Device Assignment Types
export interface DeviceIdentifier {
  lab_name: string;
  name: string;
}

export interface StaticDeviceAssignment {
  lab_name: string;
  name: string;
}

export interface DynamicDeviceAssignment {
  allocation_type: 'dynamic';
  device_type: string;
  allowed_labs?: string[];
  allowed_devices?: DeviceIdentifier[];
}

export type DeviceAssignment = StaticDeviceAssignment | DynamicDeviceAssignment | string;

// Resource Assignment Types
export type StaticResourceAssignment = string;

export interface DynamicResourceAssignment {
  allocation_type: 'dynamic';
  resource_type: string;
}

export type ResourceAssignment = StaticResourceAssignment | DynamicResourceAssignment;

export interface TaskNode {
  name: string;
  type: string;
  position: { x: number; y: number };
  devices?: Record<string, DeviceAssignment>;
  resources?: Record<string, ResourceAssignment>;
  parameters?: Record<string, string | number | boolean>;
  dependencies?: string[];
  color?: string;
  desc?: string;
  duration?: number;
  group?: string;
  device_holds?: Record<string, boolean>;
  resource_holds?: Record<string, boolean>;
}

export interface ExperimentDefinition {
  type: string;
  desc: string;
  labs: string[];
  tasks: TaskNode[];
}

export interface TaskNodeData extends Record<string, unknown> {
  taskNode: TaskNode;
  taskSpec: TaskSpec;
  isMissingSpec?: boolean;
  onNodeClick: (nodeName: string) => void;
  onNodeContextMenu: (event: React.MouseEvent, nodeName: string) => void;
}
