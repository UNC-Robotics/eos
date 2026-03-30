interface AssignmentModeSelectorProps {
  mode: 'static' | 'dynamic' | 'reference';
  onChange: (mode: 'static' | 'dynamic' | 'reference') => void;
  color?: 'blue' | 'green';
}

export function AssignmentModeSelector({ mode, onChange, color = 'blue' }: AssignmentModeSelectorProps) {
  const activeColor = color === 'blue' ? 'bg-blue-600 dark:bg-yellow-500' : 'bg-green-600 dark:bg-yellow-500';
  const activeTextColor = color === 'blue' ? 'text-white dark:text-slate-900' : 'text-white dark:text-slate-900';

  return (
    <div className="flex gap-2">
      {(['static', 'dynamic', 'reference'] as const).map((m) => (
        <button
          key={m}
          type="button"
          onClick={() => onChange(m)}
          className={`flex-1 px-3 py-2 text-xs font-medium rounded-md transition-colors capitalize ${
            mode === m
              ? `${activeColor} ${activeTextColor}`
              : 'bg-gray-100 dark:bg-slate-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-slate-600'
          }`}
        >
          {m}
        </button>
      ))}
    </div>
  );
}
