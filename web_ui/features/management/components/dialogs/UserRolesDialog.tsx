'use client';

import * as React from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { ErrorBox } from '@/components/ui/ErrorBox';
import { Label } from '@/components/ui/Label';
import { Modal } from '@/components/ui/Modal';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/Select';
import { assignRole, revokeRole, setSuperuser, type ManagedUser } from '../../api/users';

interface UserRolesDialogProps {
  user: ManagedUser | null;
  onOpenChange: (open: boolean) => void;
  labNames: string[];
}

const ROLE_OPTIONS = [
  { value: 'VIEWER', label: 'Viewer' },
  { value: 'SUBMITTER', label: 'Submitter' },
  { value: 'EDITOR', label: 'Editor' },
  { value: 'LAB_ADMIN', label: 'Lab admin' },
];

export function UserRolesDialog({ user, onOpenChange, labNames }: UserRolesDialogProps) {
  const [newRole, setNewRole] = React.useState('VIEWER');
  const [newLab, setNewLab] = React.useState('');
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    setNewLab(labNames[0] ?? '');
  }, [labNames]);

  if (!user) return null;

  const run = async (action: () => Promise<{ success: boolean; error?: string }>) => {
    setIsSubmitting(true);
    setError(null);
    const result = await action();
    setIsSubmitting(false);
    if (!result.success) setError(result.error ?? 'Operation failed');
  };

  return (
    <Modal
      open
      onOpenChange={(next) => !next && onOpenChange(false)}
      title={`Roles: ${user.username}`}
      closeDisabled={isSubmitting}
    >
      <div className="space-y-4">
        <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
          <input
            type="checkbox"
            checked={user.superuser}
            onChange={(e) => run(() => setSuperuser(user.userId, e.target.checked))}
            disabled={isSubmitting}
            className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-600 dark:border-slate-600 dark:bg-slate-800"
          />
          Superuser (all permissions)
        </label>

        <div className="space-y-1.5">
          <Label>Roles</Label>
          {user.roles.length === 0 ? (
            <p className="text-sm text-gray-500 dark:text-gray-400">No roles assigned.</p>
          ) : (
            <ul className="space-y-1">
              {user.roles.map((role) => (
                <li key={role.id} className="flex items-center justify-between text-sm">
                  <span className="flex items-center gap-2">
                    <Badge variant="info">{role.role.toLowerCase()}</Badge>
                    {role.labName && <span className="text-gray-500 dark:text-gray-400">{role.labName}</span>}
                  </span>
                  <button
                    onClick={() => run(() => revokeRole(role.id))}
                    disabled={isSubmitting}
                    className="text-gray-400 hover:text-red-600 disabled:pointer-events-none disabled:opacity-50"
                    aria-label="Revoke role"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="space-y-1.5">
          <Label>Add role</Label>
          <div className="flex items-center gap-2">
            <Select value={newRole} onValueChange={setNewRole} disabled={isSubmitting}>
              <SelectTrigger className="h-9 flex-1 text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ROLE_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {newRole === 'LAB_ADMIN' && (
              <Select value={newLab} onValueChange={setNewLab} disabled={isSubmitting}>
                <SelectTrigger className="h-9 flex-1 text-sm">
                  <SelectValue placeholder="Select lab" />
                </SelectTrigger>
                <SelectContent>
                  {labNames.map((lab) => (
                    <SelectItem key={lab} value={lab}>
                      {lab}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            <Button
              size="sm"
              className="h-9"
              onClick={() => run(() => assignRole(user.userId, newRole, newRole === 'LAB_ADMIN' ? newLab : undefined))}
              disabled={isSubmitting || (newRole === 'LAB_ADMIN' && !newLab)}
            >
              <Plus className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {error && <ErrorBox error={error} />}
      </div>
    </Modal>
  );
}
