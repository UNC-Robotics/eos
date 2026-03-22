interface JsonDisplayProps {
  data: unknown;
  label?: string;
}

export function JsonDisplay({ data, label }: JsonDisplayProps) {
  if (!data || (typeof data === 'object' && Object.keys(data).length === 0)) {
    return (
      <div className="text-sm text-gray-500 dark:text-gray-400 italic">
        {label ? `No ${label.toLowerCase()}` : 'No data'}
      </div>
    );
  }

  return (
    <div className="space-y-1">
      {label && (
        <div className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">{label}</div>
      )}
      <pre className="bg-gray-50 dark:bg-slate-900 border border-gray-200 dark:border-slate-700 rounded-md p-3 text-xs overflow-x-auto dark:text-gray-300">
        <code>{JSON.stringify(data, null, 2)}</code>
      </pre>
    </div>
  );
}
