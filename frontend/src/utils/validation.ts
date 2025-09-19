type ValidationResult = string | null;

function isNotEmpty(value: string): ValidationResult {
    return value.trim() === '' ? 'Must provide a value' : null;
}

function isNumber(value: string): ValidationResult {
    return isNaN(Number(value)) ? 'Must be a number' : null;
}

function isPositiveNumber(value: string): ValidationResult {
    const num = Number(value);
    return num > 0 ? null : 'Must be positive (> 0)';
}

function isNonNegativeNumber(value: string): ValidationResult {
    const num = Number(value);
    return num >= 0 ? null : 'Must be non-negative (≥ 0)';
}

function isInRange(min: number, max: number) {
    return (value: string): ValidationResult => {
        const num = Number(value);
        return num >= min && num <= max ? null : `Must be between ${min} and ${max}`;
    };
}

function combineValidators(...validators: ((value: string) => ValidationResult)[]) {
    return (value: string): ValidationResult => {
        for (const validator of validators) {
            const result = validator(value);
            if (result !== null) {
                return result;
            }
        }
        return null;
    };
}

export const validators = {
    // Preset common validators
    positiveNumber : combineValidators(isNotEmpty,isNumber, isPositiveNumber),
    nonNegativeNumber : combineValidators(isNotEmpty,isNumber, isNonNegativeNumber),
    percent: combineValidators(isNotEmpty,isNumber, isInRange(0, 100)),

    // Factory for range validator
    range: (min: number, max: number) => combineValidators(isNotEmpty, isNumber, isInRange(min, max)),

}