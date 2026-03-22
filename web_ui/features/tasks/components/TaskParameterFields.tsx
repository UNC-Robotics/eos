import { memo } from 'react';
import { ParameterSpec } from '@/lib/types/experiment';
import {
  NumericParameterField,
  StringParameterField,
  BooleanParameterField,
  ChoiceParameterField,
  ListParameterField,
  DictParameterField,
} from './parameter-fields';

interface TaskParameterFieldsProps {
  parameters: Record<string, ParameterSpec>;
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

  return (
    <div className="space-y-2.5">
      {Object.entries(parameters).map(([name, spec]) => (
        <ParameterField
          key={name}
          name={name}
          spec={spec}
          value={values[name]}
          onChange={(value) => onChange(name, value)}
        />
      ))}
    </div>
  );
});

TaskParameterFields.displayName = 'TaskParameterFields';
