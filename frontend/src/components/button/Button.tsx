import { memo, type ButtonHTMLAttributes, type ComponentType, type SVGAttributes } from 'react';
import { Button as MantineButton } from '@mantine/core';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  text?: string;
  icon: ComponentType<SVGAttributes<SVGSVGElement>>;
  iconSide?: 'left' | 'right';
  size?: 'default' | 'large';
}

/** Compatibility adapter for existing tool pages; Mantine owns button behavior. */
export const Button = memo(
  ({ text, icon: Icon, iconSide = 'left', size = 'default', ...props }: ButtonProps) => (
    <MantineButton
      size={size === 'large' ? 'lg' : 'sm'}
      variant="light"
      leftSection={iconSide === 'left' ? <Icon width={20} height={20} aria-hidden /> : undefined}
      rightSection={iconSide === 'right' ? <Icon width={20} height={20} aria-hidden /> : undefined}
      {...props}
    >
      {text}
    </MantineButton>
  ),
);
