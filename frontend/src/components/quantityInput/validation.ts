import { createContext, type Dispatch, type SetStateAction } from 'react';

/** Field-local incomplete values block saving without entering the API model. */
export const QuantityValidationContext = createContext<Dispatch<
  SetStateAction<Set<string>>
> | null>(null);
