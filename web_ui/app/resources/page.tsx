import { getResources } from '@/features/resources/api/resources';
import { ResourcesTable } from '@/features/resources/components/ResourcesTable';

export const dynamic = 'force-dynamic';

export default async function ResourcesPage() {
  const initialData = await getResources();

  return (
    <div className="container mx-auto p-6">
      <ResourcesTable initialData={initialData} />
    </div>
  );
}
