import {
  MantineThemeProvider,
  Modal as MantineModal,
  type ModalProps,
} from '@mantine/core';
import { overlayLayers } from '../../styles/theme';

const modalTheme = {
  components: {
    Popover: {
      defaultProps: { zIndex: overlayLayers.modalDropdown, hideDetached: true },
    },
    Menu: { defaultProps: { zIndex: overlayLayers.modalDropdown } },
  },
};

/** Portalled selects stay above their dialog; page selects stay below the header. */
export function Modal(props: ModalProps) {
  return (
    <MantineThemeProvider theme={modalTheme}>
      <MantineModal zIndex={overlayLayers.modal} {...props} />
    </MantineThemeProvider>
  );
}
