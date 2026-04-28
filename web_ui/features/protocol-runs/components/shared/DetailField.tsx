import { cn } from '@/lib/utils';
import { DETAIL_LABEL, DETAIL_VALUE } from '../../styles';

interface DetailFieldProps {
  label: string;
  value: React.ReactNode;
  className?: string;
  inline?: boolean;
}

export function DetailField({ label, value, className, inline }: DetailFieldProps) {
  if (inline) {
    return (
      <div className={cn('flex items-center justify-between gap-2 text-sm', className)}>
        <span className="text-gray-500 dark:text-gray-400 flex-shrink-0">{label}:</span>
        <span className="text-gray-900 dark:text-gray-100 font-medium text-right break-words min-w-0">{value}</span>
      </div>
    );
  }

  return (
    <div className={className}>
      <div className={DETAIL_LABEL}>{label}</div>
      <div className={cn(DETAIL_VALUE, 'break-words')}>{value}</div>
    </div>
  );
}
