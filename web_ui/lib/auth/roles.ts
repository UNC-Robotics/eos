// Role hierarchy, the single source of truth shared by the server (authz) and client (UI affordances).
// A held role satisfies a minimum requirement when its rank is at least as high. Mirrors the EOS API's
// ROLE_RANK in eos/auth/authorization.py.

export type RoleName = 'SUPERUSER' | 'LAB_ADMIN' | 'EDITOR' | 'SUBMITTER' | 'VIEWER';

const ROLE_RANK: Record<RoleName, number> = { VIEWER: 1, SUBMITTER: 2, EDITOR: 3, LAB_ADMIN: 4, SUPERUSER: 5 };

/** True if any held role meets the minimum role requirement. */
export function rolesSatisfy(roles: readonly RoleName[], minimum: RoleName): boolean {
  const required = ROLE_RANK[minimum];
  return roles.some((role) => (ROLE_RANK[role] ?? 0) >= required);
}

/** Split role rows into the superuser flag and the remaining per-instance roles (superuser is shown separately). */
export function partitionSuperuser<T extends { role: string }>(rows: T[]): { superuser: boolean; roles: T[] } {
  return {
    superuser: rows.some((r) => r.role === 'SUPERUSER'),
    roles: rows.filter((r) => r.role !== 'SUPERUSER'),
  };
}
