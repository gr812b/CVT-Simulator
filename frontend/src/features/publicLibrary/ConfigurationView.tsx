import { Accordion, Stack } from '@mantine/core';
import { BeltEditor } from '../physicalLibrary/BeltEditor';
import { EngineEditor } from '../physicalLibrary/EngineEditor';
import { CvtEditor } from '../physicalLibrary/CvtEditor';
import { VehicleEditor } from '../physicalLibrary/VehicleEditor';
import type { PhysicalDocument, PhysicalField } from '../physicalLibrary/api';
import styles from './ConfigurationView.module.css';

/** The same measurement labels and units used by the physical editor. */
export function ConfigurationView({
  document,
  fields,
}: {
  document: PhysicalDocument;
  fields: PhysicalField[];
}) {
  const cvt =
    document.kind === 'setups'
      ? document.data.cvt.data
      : document.kind === 'cvts'
        ? document.data
        : null;
  return (
    <Accordion multiple variant="separated" className={styles.configuration}>
      {document.kind === 'setups' && (
        <Accordion.Item value="vehicle">
          <Accordion.Control>Vehicle & drivetrain</Accordion.Control>
          <Accordion.Panel>
            <VehicleEditor
              value={document.data.vehicle}
              onChange={() => {}}
              disabled
            />
          </Accordion.Panel>
        </Accordion.Item>
      )}
      {document.kind === 'setups' && (
        <Accordion.Item value="engine">
          <Accordion.Control>
            Engine · {document.data.engine.name}
          </Accordion.Control>
          <Accordion.Panel>
            <EngineEditor
              value={document.data.engine.data}
              onChange={() => {}}
              disabled
            />
          </Accordion.Panel>
        </Accordion.Item>
      )}
      {document.kind === 'engines' && (
        <Accordion.Item value="engine">
          <Accordion.Control>Engine torque curve & inertia</Accordion.Control>
          <Accordion.Panel>
            <EngineEditor value={document.data} onChange={() => {}} disabled />
          </Accordion.Panel>
        </Accordion.Item>
      )}
      {document.kind === 'belts' && (
        <Accordion.Item value="belt">
          <Accordion.Control>Belt dimensions & density</Accordion.Control>
          <Accordion.Panel>
            <BeltEditor value={document.data} onChange={() => {}} disabled />
          </Accordion.Panel>
        </Accordion.Item>
      )}
      {cvt && (
        <Accordion.Item value="cvt">
          <Accordion.Control>CVT & belt measurements</Accordion.Control>
          <Accordion.Panel>
            <Stack>
              <CvtEditor
                value={cvt}
                onChange={() => {}}
                fields={fields}
                belts={[]}
                disabled
              />
            </Stack>
          </Accordion.Panel>
        </Accordion.Item>
      )}
    </Accordion>
  );
}
