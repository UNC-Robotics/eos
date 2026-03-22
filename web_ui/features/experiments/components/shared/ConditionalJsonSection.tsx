import { JsonDisplay } from '@/components/ui/JsonDisplay';
import { hasNonEmptyObject } from '@/lib/utils/experimentHelpers';
import { SECTION_DIVIDER } from '../../styles';

interface ConditionalJsonSectionProps {
  data: unknown;
  label: string;
}

export function ConditionalJsonSection({ data, label }: ConditionalJsonSectionProps) {
  if (!hasNonEmptyObject(data)) return null;

  return (
    <div className={SECTION_DIVIDER}>
      <JsonDisplay data={data} label={label} />
    </div>
  );
}
