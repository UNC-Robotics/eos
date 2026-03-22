/**
 * Task device assignment component - wrapper around unified DeviceAssignment
 * This version only supports static and dynamic modes (no reference mode)
 */
import { DeviceAssignment } from '@/features/experiment-editor/components/DeviceAssignment';
import type { DeviceAssignment as DeviceAssignmentType, DeviceSpec } from '@/lib/types/experiment';
import type { LabSpec } from '@/lib/api/specs';

interface TaskDeviceAssignmentProps {
  deviceName: string;
  deviceSpec: DeviceSpec;
  value: DeviceAssignmentType | undefined;
  onChange: (value: DeviceAssignmentType) => void;
  labSpecs: Record<string, LabSpec>;
  selectedLabs: string[];
}

export function TaskDeviceAssignment(props: TaskDeviceAssignmentProps) {
  return <DeviceAssignment {...props} enableReferenceMode={false} />;
}
