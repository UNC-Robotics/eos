import { browseFiles } from '@/features/files/api/files';
import { FileBrowser } from '@/features/files/components/FileBrowser';

export default async function FilesPage() {
  const initialData = await browseFiles('');

  return (
    <div className="container mx-auto p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Files</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Browse and manage files in object storage</p>
      </div>
      <FileBrowser initialData={initialData} />
    </div>
  );
}
