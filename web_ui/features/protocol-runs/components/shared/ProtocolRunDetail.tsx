import { Badge, getStatusBadgeVariant } from '@/components/ui/Badge';
import type { ProtocolRun } from '@/lib/types/api';
import { DetailField } from './DetailField';
import { TimelineSection } from './TimelineEntry';
import { ConditionalJsonSection } from './ConditionalJsonSection';
import { ErrorBox } from '@/components/ui/ErrorBox';
import { SECTION_DIVIDER } from '../../styles';

interface ProtocolRunDetailProps {
  protocolRun: ProtocolRun;
}

export function ProtocolRunDetail({ protocolRun }: ProtocolRunDetailProps) {
  const timelineEntries = [
    { label: 'Created', timestamp: protocolRun.created_at ?? null },
    { label: 'Started', timestamp: protocolRun.start_time ?? null },
    { label: 'Ended', timestamp: protocolRun.end_time ?? null },
  ];

  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <DetailField label="Type" value={protocolRun.type} />
        <DetailField
          label="Status"
          value={<Badge variant={getStatusBadgeVariant(protocolRun.status)}>{protocolRun.status}</Badge>}
        />
        {protocolRun.status === 'FAILED' && protocolRun.error_message && <ErrorBox error={protocolRun.error_message} />}
        <DetailField label="Owner" value={protocolRun.owner} />
        <DetailField label="Priority" value={protocolRun.priority} />
        {protocolRun.campaign && <DetailField label="Campaign" value={protocolRun.campaign} />}
      </div>

      <div className={SECTION_DIVIDER}>
        <div className="text-sm font-medium text-gray-900 dark:text-white mb-2">Timeline</div>
        <TimelineSection entries={timelineEntries} />
      </div>

      <ConditionalJsonSection data={protocolRun.parameters} label="Parameters" />
      <ConditionalJsonSection
        data={(protocolRun as { input_resources?: Record<string, unknown> }).input_resources}
        label="Input Resources"
      />
      <ConditionalJsonSection
        data={(protocolRun as { output_parameters?: Record<string, unknown> }).output_parameters}
        label="Output Parameters"
      />
      <ConditionalJsonSection
        data={(protocolRun as { output_resources?: Record<string, unknown> }).output_resources}
        label="Output Resources"
      />
      <ConditionalJsonSection data={protocolRun.meta} label="Metadata" />
    </div>
  );
}
