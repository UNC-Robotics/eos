import { Badge, getStatusBadgeVariant } from '@/components/ui/Badge';
import type { Experiment } from '@/lib/types/api';
import { DetailField } from './DetailField';
import { TimelineSection } from './TimelineEntry';
import { ConditionalJsonSection } from './ConditionalJsonSection';
import { SECTION_DIVIDER } from '../../styles';

interface ExperimentDetailProps {
  experiment: Experiment;
}

export function ExperimentDetail({ experiment }: ExperimentDetailProps) {
  const timelineEntries = [
    { label: 'Created', timestamp: experiment.created_at ?? null },
    { label: 'Started', timestamp: experiment.start_time ?? null },
    { label: 'Ended', timestamp: experiment.end_time ?? null },
  ];

  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <DetailField label="Type" value={experiment.type} />
        <DetailField
          label="Status"
          value={<Badge variant={getStatusBadgeVariant(experiment.status)}>{experiment.status}</Badge>}
        />
        {experiment.status === 'FAILED' && experiment.error_message && (
          <div className="bg-red-50 dark:bg-red-950/50 border border-red-200 dark:border-red-800 rounded-lg p-3">
            <div className="text-xs font-medium text-red-800 dark:text-red-300 mb-1">Error</div>
            <p className="text-xs text-red-700 dark:text-red-400 whitespace-pre-wrap break-words font-mono">
              {experiment.error_message}
            </p>
          </div>
        )}
        <DetailField label="Owner" value={experiment.owner} />
        <DetailField label="Priority" value={experiment.priority} />
        {experiment.campaign && <DetailField label="Campaign" value={experiment.campaign} />}
      </div>

      <div className={SECTION_DIVIDER}>
        <div className="text-sm font-medium text-gray-900 dark:text-white mb-2">Timeline</div>
        <TimelineSection entries={timelineEntries} />
      </div>

      <ConditionalJsonSection data={experiment.parameters} label="Parameters" />
      <ConditionalJsonSection
        data={(experiment as { input_resources?: Record<string, unknown> }).input_resources}
        label="Input Resources"
      />
      <ConditionalJsonSection
        data={(experiment as { output_parameters?: Record<string, unknown> }).output_parameters}
        label="Output Parameters"
      />
      <ConditionalJsonSection
        data={(experiment as { output_resources?: Record<string, unknown> }).output_resources}
        label="Output Resources"
      />
      <ConditionalJsonSection data={experiment.meta} label="Metadata" />
    </div>
  );
}
