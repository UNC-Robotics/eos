import { EditorClient } from '@/features/editor/components/EditorClient';
import { getTaskSpecs, getLabSpecs } from '@/lib/api/specs';
import type { Package, EntityType } from '@/lib/types/filesystem';
import type { ParameterSpec } from '@/lib/types/experiment';

export const metadata = {
  title: 'Editor',
  description: 'Edit EOS packages, experiments, devices, tasks, and labs',
};

async function getPackages(): Promise<Package[]> {
  try {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:3000';
    const response = await fetch(`${baseUrl}/api/filesystem/packages`, {
      cache: 'no-store',
    });

    if (!response.ok) {
      console.error('Failed to fetch packages:', response.statusText);
      return [];
    }

    return response.json();
  } catch (error) {
    console.error('Error fetching packages:', error);
    return [];
  }
}

interface EditorPageProps {
  searchParams: Promise<{
    pkg?: string;
    type?: string;
    name?: string;
    mode?: string;
  }>;
}

export default async function EditorPage({ searchParams }: EditorPageProps) {
  // Await searchParams
  const params = await searchParams;

  // Fetch packages and specs in parallel
  const [packages, taskSpecs, labSpecs] = await Promise.all([getPackages(), getTaskSpecs(), getLabSpecs()]);

  // Transform task specs for experiment editor (keep existing logic)
  const taskSpecsArray = Object.entries(taskSpecs).map(([type, spec]) => {
    const deviceTypes = spec.devices ? Array.from(new Set(Object.values(spec.devices).map((d) => d.type))) : [];

    const transformedDevices = spec.devices
      ? Object.fromEntries(Object.entries(spec.devices).map(([key, device]) => [key, { type: device.type, desc: '' }]))
      : undefined;

    const transformedInputResources = spec.input_resources
      ? Object.fromEntries(
          Object.entries(spec.input_resources).map(([key, resource]) => [key, { type: resource.type, desc: '' }])
        )
      : {};

    const transformedOutputResources = spec.output_resources
      ? Object.fromEntries(
          Object.entries(spec.output_resources).map(([key, resource]) => [key, { type: resource.type, desc: '' }])
        )
      : {};

    return {
      type,
      desc: spec.desc || '',
      device_types: deviceTypes,
      packageName: spec.packageName,
      input_devices: transformedDevices,
      output_devices: {},
      input_resources: transformedInputResources,
      output_resources: transformedOutputResources,
      input_parameters: (spec.input_parameters as Record<string, ParameterSpec>) || {},
      output_parameters: (spec.output_parameters as Record<string, ParameterSpec>) || {},
    };
  });

  // Prepare initial selection from URL params
  const initialSelection =
    params.pkg && params.type && params.name
      ? {
          packageName: params.pkg,
          entityType: params.type as EntityType,
          entityName: params.name,
          editorMode: (params.mode as 'code' | 'visual') || undefined,
        }
      : undefined;

  return (
    <EditorClient
      initialPackages={packages}
      taskSpecs={taskSpecsArray}
      labSpecs={labSpecs}
      initialSelection={initialSelection}
    />
  );
}
