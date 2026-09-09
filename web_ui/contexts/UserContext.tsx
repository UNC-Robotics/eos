'use client';

import { createContext, useContext, type ReactNode } from 'react';
import { rolesSatisfy, type RoleName } from '@/lib/auth/roles';

export interface CurrentUser {
  sub: string;
  name?: string | null;
  email?: string | null;
  superuser: boolean;
  roles: string[];
  authEnabled: boolean;
}

// Defaults match auth-disabled mode
const DEFAULT_USER: CurrentUser = {
  sub: 'dev',
  name: 'Dev User',
  superuser: true,
  roles: [],
  authEnabled: false,
};

const UserContext = createContext<CurrentUser>(DEFAULT_USER);

export function UserProvider({ user, children }: { user: CurrentUser | null; children: ReactNode }) {
  return <UserContext.Provider value={user ?? DEFAULT_USER}>{children}</UserContext.Provider>;
}

export function useUser(): CurrentUser & { canSubmit: boolean; canEdit: boolean; isAdmin: boolean } {
  const user = useContext(UserContext);
  const roles = user.roles as RoleName[];
  const canSubmit = user.superuser || rolesSatisfy(roles, 'SUBMITTER');
  const canEdit = user.superuser || rolesSatisfy(roles, 'EDITOR');
  const isAdmin = user.superuser || rolesSatisfy(roles, 'LAB_ADMIN');
  return { ...user, canSubmit, canEdit, isAdmin };
}
