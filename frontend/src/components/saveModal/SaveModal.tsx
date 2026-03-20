import { useState, useEffect } from 'react';
import { BaseModal } from '@components/baseModal/BaseModal';
import { Button } from '@components/button/Button';
import { InputField } from '@components/inputField/InputField';
import type { ParameterState } from '@types';
import { saveSimulation, simulationNameExists } from '@utils/localStorage';
import Save from '@assets/icons/edit.svg?react';
import ArrowLeft from '@assets/icons/arrow_left.svg?react';
import styles from './SaveModal.module.scss';

interface SaveModalProps {
  isOpen: boolean;
  onClose: () => void;
  parameters: ParameterState;
  onSave: () => void;
  initialName?: string;
}

export const SaveModal = ({
  isOpen,
  onClose,
  parameters,
  onSave,
  initialName = '',
}: SaveModalProps) => {
  const [name, setName] = useState(initialName);
  const [error, setError] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);

  // Reset state when modal opens
  useEffect(() => {
    if (isOpen) {
      setName(initialName);
      setError(null);
      setTouched(false);
    }
  }, [isOpen, initialName]);

  // Validate name
  useEffect(() => {
    if (!touched) return;

    if (!name.trim()) {
      setError('Name is required');
    } else if (name.trim().length < 3) {
      setError('Name must be at least 3 characters');
    } else if (simulationNameExists(name.trim())) {
      setError('A parameter set with this name already exists');
    } else {
      setError(null);
    }
  }, [name, touched]);

  const handleSave = () => {
    setTouched(true);

    if (!name.trim()) {
      setError('Name is required');
      return;
    }

    if (name.trim().length < 3) {
      setError('Name must be at least 3 characters');
      return;
    }

    if (simulationNameExists(name.trim())) {
      setError('A parameter set with this name already exists');
      return;
    }

    try {
      saveSimulation(name.trim(), parameters);
      onSave();
      onClose();
    } catch {
      setError('Failed to save parameters. Please try again.');
    }
  };

  const handleCancel = () => {
    onClose();
  };

  const jsonPreview = JSON.stringify(parameters, null, 2);

  return (
    <BaseModal
      isOpen={isOpen}
      onClose={onClose}
      title="Save Simulation Parameters"
      width="large"
      closeOnOverlayClick={false}
    >
      <div className={styles.saveModal}>
        <div className={styles.nameSection}>
          <InputField
            label="Parameter Set Name"
            value={name}
            error={touched && error ? error : null}
            onChange={(e) => setName(e.target.value)}
            onBlur={() => setTouched(true)}
            placeholder="Enter a name for this parameter set"
            autoFocus
          />
        </div>

        <div className={styles.previewSection}>
          <label className={styles.previewLabel}>Parameter Preview (JSON)</label>
          <div className={styles.jsonPreview}>
            <pre className={styles.jsonContent}>{jsonPreview}</pre>
          </div>
        </div>

        <div className={styles.buttonGroup}>
          <Button
            text="Cancel"
            icon={ArrowLeft}
            onClick={handleCancel}
            className={styles.cancelButton}
          />
          <Button
            text="Save"
            icon={Save}
            onClick={handleSave}
            disabled={!name.trim() || (touched && !!error)}
          />
        </div>
      </div>
    </BaseModal>
  );
};
