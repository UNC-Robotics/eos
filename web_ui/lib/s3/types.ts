export interface FileEntry {
  name: string;
  key: string;
  size: number;
  lastModified: string | null;
  isFolder: boolean;
}

export interface BrowseResult {
  prefix: string;
  entries: FileEntry[];
  continuationToken: string | null;
}
