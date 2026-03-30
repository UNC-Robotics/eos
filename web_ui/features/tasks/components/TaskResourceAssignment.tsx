/**
 * Task resource assignment component - wrapper around unified ResourceAssignment
 * This version only supports static and dynamic modes (no reference mode)
 */
import { ResourceAssignment } from '@/features/protocol-editor/components/ResourceAssignment';
import type { ResourceAssignment as ResourceAssignmentType, ResourceSpec } from '@/lib/types/protocol';
import type { LabSpec } from '@/lib/api/specs';

interface TaskResourceAssignmentProps {
  resourceName: string;
  resourceSpec: ResourceSpec;
  value: ResourceAssignmentType | undefined;
  onChange: (value: ResourceAssignmentType) => void;
  labSpecs: Record<string, LabSpec>;
  selectedLabs: string[];
}

export function TaskResourceAssignment(props: TaskResourceAssignmentProps) {
  return <ResourceAssignment {...props} enableReferenceMode={false} />;
}
