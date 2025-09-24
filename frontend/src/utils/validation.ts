type ValidationResult = string | null;

function isNotEmpty(value: string): ValidationResult {
    return value.trim() === '' ? 'Must provide a value' : null;
}

function isNumber(value: string): ValidationResult {
    return isNaN(Number(value)) ? 'Must be a number' : null;
}

function isGreaterThan(min: number) {
    return (value: string): ValidationResult => {
        const num = Number(value);
        return num > min ? null : `Must be greater than ${min}`;
    };
}

function isGreaterThanOrEqual(min: number) {
    return (value: string): ValidationResult => {
        const num = Number(value);
        return num >= min ? null : `Must be greater than or equal to ${min}`;
    };
}

function isLessThan(max: number) {
    return (value: string): ValidationResult => {
        const num = Number(value);
        return num < max ? null : `Must be less than ${max}`;
    };
}

function isLessThanOrEqual(max: number) {
    return (value: string): ValidationResult => {
        const num = Number(value);
        return num <= max ? null : `Must be less than or equal to ${max}`;
    };
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
    gtZero: combineValidators(isNotEmpty, isNumber, isGreaterThan(0)),
    gteZero: combineValidators(isNotEmpty, isNumber, isGreaterThanOrEqual(0)),
    percent: combineValidators(isNotEmpty, isNumber, isInRange(0, 100)),

    // Factories for custom validators
    gt: (min: number) => combineValidators(isNotEmpty, isNumber, isGreaterThan(min)),
    gte: (min: number) => combineValidators(isNotEmpty, isNumber, isGreaterThanOrEqual(min)),
    lt: (max: number) => combineValidators(isNotEmpty, isNumber, isLessThan(max)),
    lte: (max: number) => combineValidators(isNotEmpty, isNumber, isLessThanOrEqual(max)),
    range: (min: number, max: number) => combineValidators(isNotEmpty, isNumber, isInRange(min, max)),

}