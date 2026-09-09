'use client';

import * as React from 'react';
import { Copy, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { ErrorBox } from '@/components/ui/ErrorBox';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import { Modal } from '@/components/ui/Modal';
import { MultiCombobox } from '@/components/ui/MultiCombobox';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/Select';
import { createUser } from '../../api/users';

interface CreateUserDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  labNames: string[];
}

const EMPTY_FORM = { username: '', email: '', givenName: '', familyName: '' };
type BaseRole = 'NONE' | 'VIEWER' | 'SUBMITTER' | 'EDITOR';
const ROLE_OPTIONS: { value: BaseRole; label: string }[] = [
  { value: 'NONE', label: 'None' },
  { value: 'VIEWER', label: 'Viewer' },
  { value: 'SUBMITTER', label: 'Submitter' },
  { value: 'EDITOR', label: 'Editor' },
];

export function CreateUserDialog({ open, onOpenChange, labNames }: CreateUserDialogProps) {
  const [form, setForm] = React.useState(EMPTY_FORM);
  const [superuser, setSuperuser] = React.useState(false);
  const [role, setRole] = React.useState<BaseRole>('NONE');
  const [adminLabs, setAdminLabs] = React.useState<string[]>([]);
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [temporaryPassword, setTemporaryPassword] = React.useState<string | null>(null);

  const labOptions = React.useMemo(() => labNames.map((l) => ({ value: l, label: l })), [labNames]);

  const reset = () => {
    setForm(EMPTY_FORM);
    setSuperuser(false);
    setRole('NONE');
    setAdminLabs([]);
    setError(null);
    setTemporaryPassword(null);
  };

  const handleClose = () => {
    if (isSubmitting) return;
    reset();
    onOpenChange(false);
  };

  const handleSubmit = async () => {
    if (!form.username || !form.email) {
      setError('Username and email are required');
      return;
    }
    setIsSubmitting(true);
    setError(null);

    // Superuser already implies all access, so the per-instance roles are only sent otherwise.
    const roles = superuser
      ? []
      : [...(role !== 'NONE' ? [{ role }] : []), ...adminLabs.map((lab) => ({ role: 'LAB_ADMIN', labName: lab }))];
    const result = await createUser({
      username: form.username,
      email: form.email,
      givenName: form.givenName || form.username,
      familyName: form.familyName || form.username,
      superuser,
      roles,
    });
    setIsSubmitting(false);

    if (result.success) {
      setTemporaryPassword(result.temporaryPassword ?? null);
    } else {
      setError(result.error ?? 'Failed to create user');
    }
  };

  const field = (key: keyof typeof EMPTY_FORM, label: string, type = 'text') => (
    <div className="space-y-1.5">
      <Label htmlFor={key}>{label}</Label>
      <Input
        id={key}
        type={type}
        value={form[key]}
        onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
        disabled={isSubmitting}
      />
    </div>
  );

  return (
    <Modal
      open={open}
      onOpenChange={(next) => !next && handleClose()}
      title={temporaryPassword ? 'User created' : 'Create user'}
      closeDisabled={isSubmitting}
    >
      {temporaryPassword ? (
        <div className="space-y-4">
          <p className="text-sm text-gray-600 dark:text-gray-300">
            Share this temporary password with the user. They must change it at first sign-in. It will not be shown
            again.
          </p>
          <div className="flex items-center gap-2 p-3 rounded-md bg-gray-100 dark:bg-slate-800 font-mono text-sm">
            <span className="flex-1 break-all">{temporaryPassword}</span>
            <button
              onClick={() => navigator.clipboard.writeText(temporaryPassword)}
              className="text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
              aria-label="Copy password"
            >
              <Copy className="w-4 h-4" />
            </button>
          </div>
          <div className="flex justify-end">
            <Button onClick={handleClose}>Done</Button>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          {field('username', 'Username')}
          {field('email', 'Email', 'email')}
          <div className="grid grid-cols-2 gap-3">
            {field('givenName', 'Given name')}
            {field('familyName', 'Family name')}
          </div>

          <div className="space-y-1.5">
            <Label>Role</Label>
            <Select value={role} onValueChange={(v) => setRole(v as BaseRole)} disabled={isSubmitting || superuser}>
              <SelectTrigger className="h-9 text-sm">
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
          </div>

          {labNames.length > 0 && (
            <div className="space-y-1.5">
              <Label>Lab admin of</Label>
              <MultiCombobox
                options={labOptions}
                value={adminLabs}
                onChange={setAdminLabs}
                placeholder="Select labs…"
                searchPlaceholder="Search labs…"
                emptyText="No labs found"
                disabled={isSubmitting || superuser}
              />
            </div>
          )}

          <label className="flex cursor-pointer items-start gap-2.5">
            <input
              type="checkbox"
              checked={superuser}
              onChange={(e) => setSuperuser(e.target.checked)}
              disabled={isSubmitting}
              className="mt-0.5 h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-600 dark:border-slate-600 dark:bg-slate-800"
            />
            <span className="text-sm">
              <span className="flex items-center gap-1.5 font-medium text-gray-900 dark:text-white">
                <ShieldCheck className="h-3.5 w-3.5 text-yellow-500" />
                Superuser
              </span>
              <span className="text-gray-500 dark:text-gray-400">Full access; overrides the roles above.</span>
            </span>
          </label>

          {error && <ErrorBox error={error} />}

          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={handleClose} disabled={isSubmitting}>
              Cancel
            </Button>
            <Button onClick={handleSubmit} disabled={isSubmitting}>
              {isSubmitting ? 'Creating…' : 'Create user'}
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
}
