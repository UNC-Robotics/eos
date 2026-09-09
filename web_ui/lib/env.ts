/**
 * Environment variable validation and type-safe access
 *
 * This file validates required environment variables at build/runtime
 * and provides type-safe access to them throughout the application.
 */

import { z } from 'zod';

// Define the schema for environment variables
const envSchema = z
  .object({
    // Database
    DATABASE_URL: z.string().url().min(1, 'DATABASE_URL is required'),

    // Orchestrator API
    ORCHESTRATOR_API_URL: z.string().url().min(1, 'ORCHESTRATOR_API_URL is required'),

    // Node environment
    NODE_ENV: z.enum(['development', 'production', 'test']).default('development'),

    // Next.js built-in variables
    NEXT_PUBLIC_APP_URL: z.string().url().optional(),

    // Authentication (Zitadel OIDC); the remaining variables are required when enabled
    AUTH_ENABLED: z
      .string()
      .optional()
      .default('false')
      .transform((v) => v === 'true'),
    AUTH_SECRET: z.string().optional(),
    AUTH_ISSUER: z.string().url().optional(),
    AUTH_CLIENT_ID: z.string().optional(),
    AUTH_ORG_ID: z.string().optional(),
    AUTH_PROJECT_ID: z.string().optional(),
    AUTH_PAT: z.string().optional(),
    AUTH_INTROSPECTION_CLIENT_ID: z.string().optional(),
    AUTH_INTROSPECTION_CLIENT_SECRET: z.string().optional(),
  })
  .superRefine((env, ctx) => {
    if (!env.AUTH_ENABLED) return;
    const required = [
      'AUTH_SECRET',
      'AUTH_ISSUER',
      'AUTH_CLIENT_ID',
      'AUTH_ORG_ID',
      'AUTH_PROJECT_ID',
      'AUTH_PAT',
    ] as const;
    for (const key of required) {
      if (!env[key]) {
        ctx.addIssue({ code: 'custom', path: [key], message: `${key} is required when AUTH_ENABLED=true` });
      }
    }
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
