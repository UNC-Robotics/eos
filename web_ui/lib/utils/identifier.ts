// Mirrors the backend identifier rule in eos/configuration/utils.py.
export const IDENTIFIER_PATTERN = /^[a-zA-Z0-9_]+(?: [a-zA-Z0-9_]+)*$/;

export const IDENTIFIER_ERROR_MESSAGE = 'Use letters, digits, or underscores. Single spaces between words are allowed.';

export function isValidIdentifier(value: string): boolean {
  return IDENTIFIER_PATTERN.test(value);
}
