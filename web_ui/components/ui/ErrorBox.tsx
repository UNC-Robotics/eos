'use client';

import * as React from 'react';
import { Copy, Check } from 'lucide-react';

interface ErrorBoxProps {
  error: string;
  className?: string;
}

export function ErrorBox({ error, className = '' }: ErrorBoxProps) {
  const [copied, setCopied] = React.useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(error);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div
      className={`relative rounded-md bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 ${className}`}
    >
      <button
        onClick={handleCopy}
        className="absolute top-2 right-2 p-1 rounded hover:bg-red-100 dark:hover:bg-red-800/50 text-red-400 dark:text-red-500 hover:text-red-600 dark:hover:text-red-300 transition-colors"
        title="Copy error"
      >
        {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
      </button>
      <div className="p-3 pr-9 max-h-64 overflow-y-auto">
        <pre className="whitespace-pre-wrap break-words font-mono text-xs text-red-800 dark:text-red-200">{error}</pre>
      </div>
    </div>
  );
}
