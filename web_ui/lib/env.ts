/**
 * Environment variable validation and type-safe access
 *
 * This file validates required environment variables at build/runtime
 * and provides type-safe access to them throughout the application.
 */

import { z } from 'zod';

// Define the schema for environment variables
const envSchema = z.object({
  // Database
  DATABASE_URL: z.string().url().min(1, 'DATABASE_URL is required'),

  // Orchestrator API
  ORCHESTRATOR_API_URL: z.string().url().min(1, 'ORCHESTRATOR_API_URL is required'),

  // Node environment
  NODE_ENV: z.enum(['development', 'production', 'test']).default('development'),

  // Next.js built-in variables
  NEXT_PUBLIC_APP_URL: z.string().url().optional(),
});

// Parse and validate environment variables
function validateEnv() {
  try {
    return envSchema.parse(process.env);
  } catch (error) {
    if (error instanceof z.ZodError) {
      const zodError = error as z.ZodError;
      const missingVars = zodError.issues.map((err) => `  - ${err.path.join('.')}: ${err.message}`).join('\n');
      throw new Error(`❌ Invalid environment variables:\n${missingVars}`);
    }
    throw error;
  }
}

// Export validated and typed environment variables
export const env = validateEnv();
