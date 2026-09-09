'use server';

/**
 * Server Actions for the user profile
 */

import { changePassword } from '@/lib/api/zitadel';
import { requireUser } from '@/lib/auth/authz';
import type { ActionResult } from '@/lib/types/management';

export async function changeOwnPassword(currentPassword: string, newPassword: string): Promise<ActionResult> {
  const user = await requireUser();
  try {
    await changePassword(user.sub, currentPassword, newPassword);
    return { success: true };
  } catch (error) {
    return { success: false, error: error instanceof Error ? error.message : 'Failed to change password' };
  }
}
