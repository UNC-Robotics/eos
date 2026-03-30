import { DETAIL_LABEL, DETAIL_VALUE } from '../../styles';

interface DetailFieldProps {
  label: string;
  value: React.ReactNode;
  className?: string;
}

export function DetailField({ label, value, className }: DetailFieldProps) {
  return (
    <div className={className}>
      <div className={DETAIL_LABEL}>{label}</div>
      <div className={DETAIL_VALUE}>{value}</div>
    </div>
  );
}
