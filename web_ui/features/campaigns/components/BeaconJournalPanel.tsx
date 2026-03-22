'use client';

import * as React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Send, ChevronDown, ChevronRight, ChevronLeft, BookOpen } from 'lucide-react';
import { Label } from '@/components/ui/Label';
import { Textarea } from '@/components/ui/Textarea';
import { Button } from '@/components/ui/Button';
import { addOptimizerInsight } from '../api/optimizer';
import { useOrchestratorConnected } from '@/contexts/OrchestratorStatusContext';

const PAGE_SIZE = 50;

interface BeaconJournalPanelProps {
  campaignName: string;
  journal: string[];
  isRunning: boolean;
  onRefresh?: () => void;
}

export function BeaconJournalPanel({ campaignName, journal, isRunning, onRefresh }: BeaconJournalPanelProps) {
  const { isConnected } = useOrchestratorConnected();
  const [expanded, setExpanded] = React.useState(false);
  const [insightText, setInsightText] = React.useState('');
  const [isSending, setIsSending] = React.useState(false);
  const [page, setPage] = React.useState(0);

  // Reset to first page when journal length changes
  React.useEffect(() => {
    setPage(0);
  }, [journal.length]);

  const handleAddInsight = async () => {
    if (!insightText.trim()) return;
    setIsSending(true);
    const result = await addOptimizerInsight(campaignName, insightText.trim());
    if (result.success) {
      setInsightText('');
      onRefresh?.();
    }
    setIsSending(false);
  };

  const disabled = !isRunning || isSending || !isConnected;

  // Pagination over reversed journal (newest first)
  const reversed = React.useMemo(() => [...journal].reverse(), [journal]);
  const totalPages = Math.max(1, Math.ceil(reversed.length / PAGE_SIZE));
  const pageEntries = reversed.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  return (
    <div className="bg-white dark:bg-slate-900 rounded-lg border border-gray-200 dark:border-slate-700 p-4">
      <button type="button" onClick={() => setExpanded(!expanded)} className="w-full flex items-center gap-2 text-left">
        {expanded ? (
          <ChevronDown className="h-4 w-4 text-gray-500" />
        ) : (
          <ChevronRight className="h-4 w-4 text-gray-500" />
        )}
        <div>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
            <BookOpen className="h-5 w-5" />
            Beacon Journal
          </h2>
          <p className="text-xs text-gray-500 dark:text-gray-400">AI reasoning log and expert insights</p>
        </div>
      </button>

      {expanded && (
        <div className="mt-4 space-y-4">
          {/* Expert Insights */}
          <div className="space-y-2">
            <Label className="text-sm font-medium">Expert Insights</Label>
            <div className="flex gap-2 items-center">
              <Textarea
                value={insightText}
                onChange={(e) => setInsightText(e.target.value)}
                placeholder="Add an expert insight..."
                disabled={disabled}
                className="text-xs min-h-[60px]"
              />
              <Button
                variant="outline"
                size="sm"
                onClick={handleAddInsight}
                disabled={disabled || !insightText.trim()}
                className="h-8 px-3 gap-1 shrink-0"
              >
                <Send className="h-3 w-3" />
                Send
              </Button>
            </div>
          </div>

          {/* Journal Entries */}
          {journal.length > 0 && (
            <div className="space-y-2">
              <Label className="text-sm font-medium">
                Journal ({journal.length} {journal.length === 1 ? 'entry' : 'entries'})
              </Label>
              <div className="max-h-96 overflow-auto border border-gray-200 dark:border-slate-700 rounded-md">
                {pageEntries.map((entry, i) => (
                  <div
                    key={page * PAGE_SIZE + i}
                    className={`px-3 py-2 text-xs text-gray-700 dark:text-gray-300 prose prose-xs dark:prose-invert max-w-none ${
                      i < pageEntries.length - 1 ? 'border-b border-gray-200 dark:border-slate-700' : ''
                    }`}
                  >
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{entry}</ReactMarkdown>
                  </div>
                ))}
              </div>

              {/* Pagination */}
              {totalPages > 1 && (
                <div className="flex items-center justify-between pt-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setPage((p) => Math.max(0, p - 1))}
                    disabled={page === 0}
                    className="h-7 px-2 gap-1"
                  >
                    <ChevronLeft className="h-3 w-3" />
                    Newer
                  </Button>
                  <span className="text-xs text-gray-500 dark:text-gray-400">
                    Page {page + 1} of {totalPages}
                  </span>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                    disabled={page === totalPages - 1}
                    className="h-7 px-2 gap-1"
                  >
                    Older
                    <ChevronRight className="h-3 w-3" />
                  </Button>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
