'use client';

import * as React from 'react';
import { ShieldCheck, Trash2, UserCog, UserPlus, UserX, UserCheck } from 'lucide-react';
import { DataTable, DataTableColumnDef } from '@/components/data-table/DataTable';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { ConfirmationDialog } from './dialogs/ConfirmationDialog';
import { CreateUserDialog } from './dialogs/CreateUserDialog';
import { UserRolesDialog } from './dialogs/UserRolesDialog';
import { deleteUser, setUserActive, type ManagedUser } from '../api/users';

interface UsersTabProps {
  initialUsers: ManagedUser[];
  labNames: string[];
}

export function UsersTab({ initialUsers, labNames }: UsersTabProps) {
  const [createOpen, setCreateOpen] = React.useState(false);
  const [rolesUser, setRolesUser] = React.useState<ManagedUser | null>(null);
  const [deleteTarget, setDeleteTarget] = React.useState<ManagedUser | null>(null);

  // Keep the roles dialog in sync after revalidation refreshes the user list
  React.useEffect(() => {
    if (rolesUser) setRolesUser(initialUsers.find((u) => u.userId === rolesUser.userId) ?? null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialUsers]);

  const columns: DataTableColumnDef<ManagedUser>[] = [
    {
      accessorKey: 'username',
      header: 'Username',
      cell: ({ row }) => <div className="font-medium">{row.getValue('username')}</div>,
    },
    {
      accessorKey: 'displayName',
      header: 'Name',
    },
    {
      accessorKey: 'email',
      header: 'Email',
    },
    {
      accessorKey: 'state',
      header: 'State',
      cell: ({ row }) => {
        const state = row.getValue('state') as string;
        return <Badge variant={state === 'ACTIVE' ? 'success' : 'default'}>{state.toLowerCase()}</Badge>;
      },
    },
    {
      id: 'roles',
      header: 'Roles',
      cell: ({ row }) => {
        const user = row.original;
        return (
          <div className="flex flex-wrap gap-1">
            {user.superuser && (
              <Badge variant="warning">
                <ShieldCheck className="w-3 h-3 mr-1" />
                superuser
              </Badge>
            )}
            {user.roles.map((role) => (
              <Badge key={role.id} variant="info">
                {role.role.toLowerCase()}
                {role.labName ? `: ${role.labName}` : ''}
              </Badge>
            ))}
            {!user.superuser && user.roles.length === 0 && (
              <span className="text-xs text-gray-400 dark:text-gray-500">no access</span>
            )}
          </div>
        );
      },
    },
    {
      id: 'actions',
      header: 'Actions',
      cell: ({ row }) => {
        const user = row.original;
        const active = user.state === 'ACTIVE';
        return (
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => setRolesUser(user)}>
              <UserCog className="h-4 w-4 mr-1" />
              Roles
            </Button>
            <Button variant="outline" size="sm" onClick={() => setUserActive(user.userId, !active)}>
              {active ? <UserX className="h-4 w-4 mr-1" /> : <UserCheck className="h-4 w-4 mr-1" />}
              {active ? 'Deactivate' : 'Reactivate'}
            </Button>
            <Button variant="outline" size="sm" onClick={() => setDeleteTarget(user)}>
              <Trash2 className="h-4 w-4 mr-1" />
              Delete
            </Button>
          </div>
        );
      },
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
          <UserPlus className="h-4 w-4 mr-1" />
          Create user
        </Button>
      </div>

      <DataTable columns={columns} data={initialUsers} searchPlaceholder="Search users..." />

      <CreateUserDialog open={createOpen} onOpenChange={setCreateOpen} labNames={labNames} />

      <UserRolesDialog user={rolesUser} onOpenChange={() => setRolesUser(null)} labNames={labNames} />

      <ConfirmationDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title="Delete user"
        description="Are you sure? This permanently deletes the account in Zitadel."
        confirmLabel="Delete"
        variant="destructive"
        items={deleteTarget ? [deleteTarget.username] : []}
        onConfirm={async () => {
          if (!deleteTarget) return;
          const result = await deleteUser(deleteTarget.userId);
          if (!result.success) throw new Error(result.error);
        }}
      />
    </div>
  );
}
