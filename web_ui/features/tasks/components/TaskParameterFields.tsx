import { memo } from 'react';
import { InputParameterEntry, ParameterSpec } from '@/lib/types/protocol';
import { iterateInputParameters } from '@/lib/utils/paramGroups';
import {
  NumericParameterField,
  StringParameterField,
  BooleanParameterField,
  ChoiceParameterField,
  ListParameterField,
  DictParameterField,
} from './parameter-fields';

interface TaskParameterFieldsProps {
  parameters: Record<string, InputParameterEntry>;
  values: Record<string, unknown>;
  onChange: (name: string, value: unknown) => void;
}

interface ParameterFieldProps {
  name: string;
  spec: ParameterSpec;
  value: unknown;
  onChange: (value: unknown) => void;
}

const ParameterField = memo(({ name, spec, value, onChange }: ParameterFieldProps) => {
  const normalizedType = spec.type.toLowerCase();

  // Route to specialized components based on type
  switch (normalizedType) {
    case 'int':
    case 'integer':
    case 'float':
    case 'number':
    case 'double':
      return <NumericParameterField name={name} spec={spec} value={value} onChange={onChange} />;

    case 'str':
    case 'string':
      return <StringParameterField name={name} spec={spec} value={value} onChange={onChange} />;

    case 'bool':
    case 'boolean':
      return <BooleanParameterField name={name} spec={spec} value={value} onChange={onChange} />;

    case 'choice':
      return <ChoiceParameterField name={name} spec={spec} value={value} onChange={onChange} />;

    case 'list':
      return <ListParameterField name={name} spec={spec} value={value} onChange={onChange} />;

    case 'dict':
    case 'dictionary':
      return <DictParameterField name={name} spec={spec} value={value} onChange={onChange} />;

    default:
      // Fallback to string field for unknown types
      return <StringParameterField name={name} spec={spec} value={value} onChange={onChange} />;
  }
});

ParameterField.displayName = 'ParameterField';

export const TaskParameterFields = memo(({ parameters, values, onChange }: TaskParameterFieldsProps) => {
  if (!parameters || Object.keys(parameters).length === 0) {
    return null;
  }

  const structure = iterateInputParameters(parameters);

  return (
    <div className="space-y-4">
      {structure.map((item) => {
        if (item.kind === 'param') {
          return (
            <ParameterField
              key={item.name}
              name={item.name}
              spec={item.spec}
              value={values[item.name]}
              onChange={(value) => onChange(item.name, value)}
            />
          );
        }
        return (
          <div key={`group-${item.name}`} className="space-y-2 pt-1">
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold uppercase tracking-wide text-black dark:text-white whitespace-nowrap">
                {item.name}
              </span>
              <div className="flex-1 h-px bg-gray-200 dark:bg-slate-700" />
            </div>
            <div className="space-y-4">
              {Object.entries(item.params).map(([name, spec]) => (
                <ParameterField
                  key={name}
                  name={name}
                  spec={spec}
                  value={values[name]}
                  onChange={(value) => onChange(name, value)}
                />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
});

TaskParameterFields.displayName = 'TaskParameterFields';
