'use server';

import { getNamesByPrefix } from '@/lib/db/queries';
import { generateUniqueCloneName } from './naming';

export async function generateCloneNameForEntity(
  entity: 'campaigns' | 'experiments' | 'tasks',
  originalName: string
): Promise<string> {
  const trailingNum = originalName.match(/(\d+)$/);
  const prefix = trailingNum ? originalName.slice(0, -trailingNum[1].length) : `${originalName}_`;
  const matchingNames = await getNamesByPrefix(entity, prefix);
  return generateUniqueCloneName(originalName, matchingNames);
}
