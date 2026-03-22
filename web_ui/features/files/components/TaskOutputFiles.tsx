'use client';

import { File, Download } from 'lucide-react';
import { startDownload } from '@/lib/transfers';

interface TaskOutputFilesProps {
  fileNames: string[];
  experimentName: string | null;
  taskName: string;
}

export function TaskOutputFiles({ fileNames, experimentName, taskName }: TaskOutputFilesProps) {
  const prefix = experimentName || 'on_demand';

  const handleDownload = (fileName: string) => {
    const key = `${prefix}/${taskName}/${fileName}`;
    startDownload(key, fileName);
  };

  const handleDownloadAll = () => {
    for (const fileName of fileNames) {
      handleDownload(fileName);
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <div className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">Output Files</div>
        {fileNames.length > 1 && (
          <button
            onClick={handleDownloadAll}
            className="text-xs text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 flex items-center gap-1"
          >
            <Download className="w-3 h-3" />
            Download all
          </button>
        )}
      </div>
      <ul className="space-y-1">
        {fileNames.map((fileName, idx) => (
          <li
            key={idx}
            className="group flex items-center justify-between py-1 px-2 rounded hover:bg-gray-50 dark:hover:bg-slate-800 transition-colors"
          >
            <div className="flex items-center gap-2 min-w-0">
              <File className="w-3.5 h-3.5 text-gray-400 dark:text-gray-500 flex-shrink-0" />
              <span className="text-sm text-gray-700 dark:text-gray-300 truncate">{fileName}</span>
            </div>
            <button
              onClick={() => handleDownload(fileName)}
              className="opacity-0 group-hover:opacity-100 text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 transition-opacity flex-shrink-0 ml-2"
              title="Download"
            >
              <Download className="w-3.5 h-3.5" />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
