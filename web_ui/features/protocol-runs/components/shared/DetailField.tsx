import { DETAIL_LABEL, DETAIL_VALUE } from '../../styles';
import { cn } from '@/lib/utils';

interface DetailFieldProps {
  label: string;
  value: React.ReactNode;
  className?: string;
}

export function DetailField({ label, value, className }: DetailFieldProps) {
  return (
    <div className={cn("text-xs text-gray-500 dark:text-gray-400 mb-1", className)}>
      <div className={cn(DETAIL_LABEL, "flex-shrink-0")}>
        {label}
      </div>

      <div className={cn(DETAIL_VALUE, "text-sm text-gray-900 dark:text-white break-words")}>
        {value}
      </div>
    </div>
  );
}
