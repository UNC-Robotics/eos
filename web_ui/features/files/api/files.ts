'use server';

import {
  browseFiles as s3Browse,
  searchFiles as s3Search,
  deleteFile as s3Delete,
  deletePrefix as s3DeletePrefix,
} from '@/lib/s3/client';
import type { BrowseResult, FileEntry } from '@/lib/s3/types';

export async function browseFiles(
  prefix: string = '',
  continuationToken?: string,
  maxKeys: number = 200
): Promise<BrowseResult> {
  return s3Browse(prefix, maxKeys, continuationToken);
}

export async function searchFiles(query: string, prefix: string = '', maxResults: number = 100): Promise<FileEntry[]> {
  return s3Search(query, prefix, maxResults);
}

export async function deleteEntry(key: string, isFolder: boolean): Promise<{ deleted: number }> {
  if (isFolder) {
    const deleted = await s3DeletePrefix(key);
    return { deleted };
  }
  await s3Delete(key);
  return { deleted: 1 };
}
