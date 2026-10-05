import { useEffect, useState } from 'react';
import { Select, type SelectProps } from '@mantine/core';
import { getSchools } from './api';

export function SchoolSelect(props: SelectProps) {
  const [schools, setSchools] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    void getSchools()
      .then((catalog) => {
        if (active) setSchools(catalog.schools);
      })
      .catch(() => {
        if (active)
          setError(
            'School list unavailable. You can leave this blank and set it later.',
          );
      });
    return () => {
      active = false;
    };
  }, []);
  return (
    <Select
      label="School"
      placeholder="Search for your school"
      searchable
      clearable
      nothingFoundMessage="No matching school"
      data={schools}
      description="Optional · schools from Baja SAE results, 2024–2026."
      {...props}
      value={props.value || null}
      error={props.error || error}
    />
  );
}
