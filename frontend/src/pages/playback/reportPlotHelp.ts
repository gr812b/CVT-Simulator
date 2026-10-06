/** Explanations for the reportGraphs definitions. Names, signs and availability
 * follow the report contract and cinder/results/balances.py. */
const axial = (side: string) => `The axial free body of the ${side} movable sheave. Belt, spring, mechanism and travel-stop forces are signed positive toward groove closure. Their sum equals the translating-mass × axial-acceleration trace; the inertia trace is the other side of the balance, not an extra applied force. Secondary opening is negative local closure. Gaps mean the quantity is unavailable in that operating regime, not zero.`;
const torque = (side: string) => `The rotational balance of the ${side} pulley assembly. External, belt and mechanism-coupling torques use the shaft’s positive rotation convention. Their sum equals the effective-inertia × angular-acceleration trace. The inertia trace is not another applied torque; the coupling term collects the mechanism’s remaining contributions.`;
export const REPORT_PLOT_HELP: Readonly<Record<string, string>> = {
  'Distance travelled': 'Vehicle distance along the road coordinate versus simulation time. This is the accumulated vehicle motion, not belt travel.',
  'Vehicle speed': 'Vehicle forward speed versus simulation time, resolved from the output shaft and drivetrain geometry.',
  'Vehicle acceleration': 'Vehicle acceleration versus time. Positive values mean increasing forward speed; negative values mean deceleration.',
  'Road-load forces': 'Rolling resistance, road-grade load, aerodynamic drag and their total, plotted against vehicle speed rather than time. The grade term may assist motion downhill. A trajectory can double back at the same speed; the playback marker selects the current recorded state.',
  'CVT ratio': 'The geometric effective-radius ratio: secondary belt radius divided by primary belt radius. It is not the measured shaft-speed ratio during slip.',
  'Ratio rate': 'Time rate of change of the effective secondary-to-primary radius ratio. A decreasing ratio corresponds to an upshift under this convention.',
  'Primary and secondary radius rates': 'How quickly each effective belt radius changes. The two rates are coupled by the belt geometry; they need not have equal magnitude.',
  'Shift curve': 'Engine speed against vehicle speed, not time. A nearly horizontal section means engine speed remains nearly constant as vehicle speed changes. The marker follows the recorded trajectory, including backshifts.',
  'Engine speed': 'Primary/engine shaft speed versus simulation time. This is a dynamic result of applied and transmitted torques, not a prescribed shift schedule.',
  'Engine torque': 'The external torque applied at the primary boundary. It is not necessarily the torque delivered to the belt, because the primary assembly and its mechanisms can accelerate.',
  'Engine power': 'Power at the primary boundary, from external primary torque and shaft speed. This is boundary power, not output power or transmission efficiency.',
  'Primary belt-normal load': 'The normal-force resultant integrated over both primary sheave faces. This is not the axial force on one movable sheave; that force includes the face projection and one-face share.',
  'Secondary belt-normal load': 'The normal-force resultant integrated over both secondary sheave faces. Do not compare it directly with one movable sheave’s axial force without the face projection and share.',
  'Belt tensions': 'Tension at the input and output of each pulley wrap. Differences carry transmitted load and belt inertia. The four endpoints need not reduce to one common tight-side value and one common slack-side value during a transient.',
  'Relative belt speed': 'Signed circumferential relative speed between each pulley and the belt, using the report’s local contact convention. Zero is compatible with sticking. Nonzero values indicate sliding; the sign identifies its direction.',
  'Belt speed': 'The belt’s transport speed around its loop versus time. It is a separate dynamic quantity and need not equal either pulley’s surface speed during sliding.',
  'Transmitted torques': 'Signed belt-interface torques at the primary and secondary. Their signs follow the model’s pulley torque convention; their magnitudes need not match across a changing transmission ratio.',
  'Traction utilization': 'The signed traction coefficient λ used by each pulley contact: tangential traction divided by its normal resultant. This is not a percentage or a value normalized to one. Sticking permits a reaction within the static-friction bounds; sliding uses the kinetic bound with the appropriate sign.',
  'Primary axial force balance': axial('primary'),
  'Secondary axial force balance': axial('secondary'),
  'Primary torque balance': torque('primary'),
  'Secondary torque balance': torque('secondary'),
  'Primary angular acceleration': 'The primary shaft’s angular acceleration from the dynamic torque balance. It is distinct from axial sheave acceleration and from flyweight arm acceleration.',
  'Secondary angular acceleration': 'The secondary shaft’s angular acceleration from the dynamic torque balance. This is shaft motion, not the movable sheave’s relative helix rotation.',
  'Primary actuator forces': 'The primary axial-spring contribution and total actuator clamping contribution. The total includes the spring; these two traces should not be added again. Use the axial force balance to include belt loading and stop reactions.',
  'Secondary actuator forces': 'The secondary axial-spring contribution and total actuator clamping contribution. The total already includes the spring. The complete movable-sheave free body also includes belt loading and stop reactions.',
  'Primary flyweight forces': 'Resolved contributions from the flyweight mechanism: centrifugal actuation, axial-inertia coupling and motion-ratio curvature. They show why a changing arm geometry affects dynamic clamping; they are not all independent external loads.',
  'Secondary helix forces': 'Resolved helix contributions from reacted belt torque, shaft acceleration, shift acceleration, shift-speed curvature and torsional preload. They show how the torque-reacting movable member couples rotation and axial motion. The axial spring is shown separately in the complete balance.',
};
