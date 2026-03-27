interface TimelineEntryProps {
  label: string;
  timestamp: string | null;
}

export function TimelineEntry({ label, timestamp }: TimelineEntryProps) {
  if (!timestamp) return null;

  return (
    <div>
      <span className="text-gray-500 dark:text-gray-400">{label}:</span>{' '}
      <span className="text-gray-900 dark:text-gray-100">{new Date(timestamp).toLocaleString()}</span>
    </div>
  );
}

interface TimelineSectionProps {
  entries: Array<{ label: string; timestamp: string | null }>;
}

export function TimelineSection({ entries }: TimelineSectionProps) {
  return (
    <div className="space-y-1 text-xs">
      {entries.map((entry) => (
        <TimelineEntry key={entry.label} label={entry.label} timestamp={entry.timestamp} />
      ))}
    </div>
  );
}
