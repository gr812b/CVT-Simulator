import { forwardRef } from 'react';
import {
  Button,
  Tooltip,
  createPolymorphicComponent,
  type ButtonProps,
} from '@mantine/core';

type Props = ButtonProps & { disabledReason?: string };

/** Disabled buttons cannot receive focus; the wrapper exposes their explanation. */
export const ActionButton = createPolymorphicComponent<'button', Props>(
  forwardRef<HTMLButtonElement, Props>(function ActionButton(
    { disabledReason, disabled, loading, ...props },
    ref,
  ) {
    const blocked = Boolean(disabled || disabledReason || loading);
    const reason = loading
      ? 'Please wait for this action to finish.'
      : (disabledReason ??
        'Complete the required inputs before using this action.');
    const button = (
      <Button {...props} ref={ref} disabled={blocked} loading={loading} />
    );
    return blocked ? (
      <Tooltip
        label={reason}
        multiline
        maw={320}
        withArrow
        events={{ hover: true, focus: true, touch: true }}
      >
        <span
          tabIndex={0}
          role="group"
          aria-label={reason}
          style={{
            display: 'inline-flex',
            maxWidth: '100%',
            width: props.fullWidth ? '100%' : undefined,
          }}
        >
          {button}
        </span>
      </Tooltip>
    ) : (
      button
    );
  }),
);
