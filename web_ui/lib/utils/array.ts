/**
 * Array utility functions
 */

/**
 * Toggle an item in an array - adds it if not present, removes it if present
 * @param list The array to toggle in
 * @param item The item to toggle
 * @param compareFn Optional comparison function for complex objects
 * @returns New array with item toggled
 */
export function toggleInArray<T>(list: T[] | undefined, item: T, compareFn?: (a: T, b: T) => boolean): T[] {
  const arr = list || [];
  const isPresent = compareFn ? arr.some((el) => compareFn(el, item)) : arr.includes(item);

  if (isPresent) {
    return compareFn ? arr.filter((el) => !compareFn(el, item)) : arr.filter((el) => el !== item);
  }

  return [...arr, item];
}

/**
 * Toggle a string in a string array
 */
export function toggleString(list: string[] | undefined, item: string): string[] {
  return toggleInArray(list, item);
}
