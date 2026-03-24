export function generateUniqueCloneName(originalName: string, existingNames: string[]): string {
  const trailingNum = originalName.match(/(\d+)$/);
  const baseName = trailingNum ? originalName.slice(0, -trailingNum[1].length) : `${originalName}_`;

  let maxNum = 0;
  for (const name of existingNames) {
    if (name.startsWith(baseName)) {
      const suffix = name.slice(baseName.length);
      if (/^\d+$/.test(suffix)) {
        maxNum = Math.max(maxNum, parseInt(suffix, 10));
      }
    }
  }

  return `${baseName}${maxNum + 1}`;
}
