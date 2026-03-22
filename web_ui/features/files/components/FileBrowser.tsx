'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import { Folder, File, Download, Upload, RefreshCw, ChevronRight, Search, Trash2, X } from 'lucide-react';
import { ConfirmDialog } from '@/components/dialogs/ConfirmDialog';
import { browseFiles, searchFiles, deleteEntry } from '../api/files';
import { startDownload, startUpload } from '@/lib/transfers';
import { formatBytes } from '@/lib/format';
import type { FileEntry, BrowseResult } from '@/lib/s3/types';

function formatDate(iso: string | null): string {
  if (!iso) return '--';
  return new Date(iso).toLocaleString();
}

interface FileBrowserProps {
  initialData: BrowseResult;
}

export function FileBrowser({ initialData }: FileBrowserProps) {
  const [prefix, setPrefix] = useState(initialData.prefix);
  const [entries, setEntries] = useState<FileEntry[]>(initialData.entries);
  const [continuationToken, setContinuationToken] = useState(initialData.continuationToken);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [isSearching, setIsSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<FileEntry[] | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<FileEntry | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const searchTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Debounced search with staleness guard
  const searchIdRef = useRef(0);

  useEffect(() => {
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current);
    }

    if (!searchQuery.trim()) {
      setSearchResults(null);
      setIsSearching(false);
      return;
    }

    setIsSearching(true);
    const currentSearchId = ++searchIdRef.current;

    searchTimeoutRef.current = setTimeout(async () => {
      try {
        const results = await searchFiles(searchQuery.trim(), prefix);
        // Discard if a newer search has been triggered
        if (currentSearchId !== searchIdRef.current) return;
        setSearchResults(results);
      } catch (error) {
        if (currentSearchId !== searchIdRef.current) return;
        console.error('Search error:', error);
        setSearchResults([]);
      } finally {
        if (currentSearchId === searchIdRef.current) {
          setIsSearching(false);
        }
      }
    }, 300);

    return () => {
      if (searchTimeoutRef.current) {
        clearTimeout(searchTimeoutRef.current);
      }
    };
  }, [searchQuery, prefix]);

  const clearSearch = useCallback(() => {
    setSearchQuery('');
    setSearchResults(null);
  }, []);

  const navigate = useCallback(async (newPrefix: string) => {
    setSearchQuery('');
    setSearchResults(null);
    setLoading(true);
    try {
      const result = await browseFiles(newPrefix);
      setPrefix(result.prefix);
      setEntries(result.entries);
      setContinuationToken(result.continuationToken);
    } catch (error) {
      console.error('Browse error:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadMore = useCallback(async () => {
    if (!continuationToken) return;
    setLoading(true);
    try {
      const result = await browseFiles(prefix, continuationToken);
      setEntries((prev) => [...prev, ...result.entries]);
      setContinuationToken(result.continuationToken);
    } catch (error) {
      console.error('Load more error:', error);
    } finally {
      setLoading(false);
    }
  }, [prefix, continuationToken]);

  const refresh = useCallback(() => navigate(prefix), [navigate, prefix]);

  const handleFileDownload = (entry: FileEntry) => {
    startDownload(entry.key, entry.name);
  };

  const handleUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files) return;
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const key = `${prefix}${file.name}`;
      startUpload(file, key);
    }
    // Reset input so the same file can be uploaded again
    event.target.value = '';

    // Refresh after a short delay to show new files
    setTimeout(refresh, 2000);
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteEntry(deleteTarget.key, deleteTarget.isFolder);
      // Remove from local state immediately
      if (searchResults !== null) {
        setSearchResults((prev) => prev?.filter((e) => e.key !== deleteTarget.key) ?? null);
      } else {
        setEntries((prev) => prev.filter((e) => e.key !== deleteTarget.key));
      }
    } catch (error) {
      console.error('Delete error:', error);
    }
    setDeleteTarget(null);
  };

  const displayEntries = searchResults !== null ? searchResults : entries;

  // Build breadcrumb segments
  const segments = prefix.split('/').filter(Boolean);
  const breadcrumbs = [
    { label: 'Root', prefix: '' },
    ...segments.map((seg, i) => ({
      label: seg,
      prefix: segments.slice(0, i + 1).join('/') + '/',
    })),
  ];

  return (
    <div>
      {/* Toolbar */}
      <div className="flex items-center justify-between mb-4">
        {/* Breadcrumb */}
        <nav className="flex items-center gap-1 text-sm text-gray-600 dark:text-gray-400 min-w-0 overflow-hidden">
          {breadcrumbs.map((crumb, i) => (
            <span key={crumb.prefix} className="flex items-center gap-1 flex-shrink-0">
              {i > 0 && <ChevronRight className="w-3.5 h-3.5 text-gray-400 dark:text-gray-500" />}
              <button
                onClick={() => navigate(crumb.prefix)}
                className={`hover:text-blue-600 dark:hover:text-blue-400 transition-colors truncate ${
                  i === breadcrumbs.length - 1 ? 'text-gray-900 dark:text-white font-medium' : ''
                }`}
              >
                {crumb.label}
              </button>
            </span>
          ))}
        </nav>

        {/* Actions */}
        <div className="flex items-center gap-2 flex-shrink-0">
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 dark:text-gray-500 pointer-events-none" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search files..."
              className="pl-8 pr-8 py-1.5 w-56 text-sm border border-gray-200 dark:border-slate-700 rounded-md bg-white dark:bg-slate-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
            {searchQuery && (
              <button
                onClick={clearSearch}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          <button
            onClick={refresh}
            disabled={loading}
            className="p-2 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-slate-800 rounded-md transition-colors"
            title="Refresh"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <button
            onClick={() => fileInputRef.current?.click()}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-blue-600 text-white dark:bg-yellow-500 dark:text-slate-900 rounded-md hover:bg-blue-700 dark:hover:bg-yellow-600 transition-colors"
          >
            <Upload className="w-4 h-4" />
            Upload
          </button>
          <input ref={fileInputRef} type="file" multiple onChange={handleUpload} className="hidden" />
        </div>
      </div>

      {/* File table */}
      <div className="border border-gray-200 dark:border-slate-700 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 dark:bg-slate-800 border-b border-gray-200 dark:border-slate-700">
              <th className="text-left px-4 py-2 font-medium text-gray-500 dark:text-gray-400">Name</th>
              <th className="text-right px-4 py-2 font-medium text-gray-500 dark:text-gray-400 w-24">Size</th>
              <th className="text-right px-4 py-2 font-medium text-gray-500 dark:text-gray-400 w-44">Last Modified</th>
              <th className="text-right px-4 py-2 font-medium text-gray-500 dark:text-gray-400 w-20">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-slate-800">
            {isSearching && (
              <tr>
                <td colSpan={4} className="text-center py-8 text-gray-400 dark:text-gray-500">
                  Searching...
                </td>
              </tr>
            )}
            {!isSearching && displayEntries.length === 0 && !loading && (
              <tr>
                <td colSpan={4} className="text-center py-8 text-gray-400 dark:text-gray-500">
                  {searchResults !== null ? 'No files match your search' : 'This folder is empty'}
                </td>
              </tr>
            )}
            {!isSearching &&
              displayEntries.map((entry) => (
                <tr key={entry.key} className="hover:bg-gray-50 dark:hover:bg-slate-800/50 transition-colors group">
                  <td className="px-4 py-2">
                    <button
                      onClick={() => (entry.isFolder ? navigate(entry.key) : handleFileDownload(entry))}
                      className="flex items-center gap-2 text-gray-900 dark:text-gray-100 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
                    >
                      {entry.isFolder ? (
                        <Folder className="w-4 h-4 text-yellow-500 flex-shrink-0" />
                      ) : (
                        <File className="w-4 h-4 text-gray-400 dark:text-gray-500 flex-shrink-0" />
                      )}
                      <span className="truncate">{entry.name}</span>
                    </button>
                  </td>
                  <td className="px-4 py-2 text-right text-gray-500 dark:text-gray-400">
                    {entry.isFolder ? '--' : formatBytes(entry.size)}
                  </td>
                  <td className="px-4 py-2 text-right text-gray-500 dark:text-gray-400">
                    {formatDate(entry.lastModified)}
                  </td>
                  <td className="px-4 py-2 text-right">
                    <div className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      {!entry.isFolder && (
                        <button
                          onClick={() => handleFileDownload(entry)}
                          className="p-1 text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 rounded transition-colors"
                          title="Download"
                        >
                          <Download className="w-4 h-4" />
                        </button>
                      )}
                      <button
                        onClick={() => setDeleteTarget(entry)}
                        className="p-1 text-gray-400 hover:text-red-600 dark:hover:text-red-400 rounded transition-colors"
                        title="Delete"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      {/* Load more */}
      {continuationToken && searchResults === null && (
        <div className="mt-4 text-center">
          <button
            onClick={loadMore}
            disabled={loading}
            className="px-4 py-2 text-sm text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 border border-blue-200 dark:border-blue-800 rounded-md hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors disabled:opacity-50"
          >
            {loading ? 'Loading...' : 'Load more'}
          </button>
        </div>
      )}

      {loading && entries.length === 0 && (
        <div className="text-center py-12 text-gray-400 dark:text-gray-500">Loading...</div>
      )}

      <ConfirmDialog
        isOpen={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
        title={deleteTarget?.isFolder ? 'Delete folder' : 'Delete file'}
        message={
          deleteTarget?.isFolder
            ? `Are you sure you want to delete the folder "${deleteTarget.name}" and all its contents? This cannot be undone.`
            : `Are you sure you want to delete "${deleteTarget?.name}"? This cannot be undone.`
        }
        confirmText="Delete"
        variant="danger"
      />
    </div>
  );
}
