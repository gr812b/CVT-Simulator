I'll analyze the ramps system, frontend input page, and API to create a comprehensive plan. Let me start by examining these components. 

Read [](file:///Users/kaiarseneau/Documents/GitHub/CVT-Simulator/cvtModel/src/cvt_simulator/models/ramps/__init__.py)

Read [](file:///Users/kaiarseneau/Documents/GitHub/CVT-Simulator/cvtModel/src/cvt_simulator/models/ramps/ramp_segment.py)

Read [](file:///Users/kaiarseneau/Documents/GitHub/CVT-Simulator/cvtModel/src/cvt_simulator/models/ramps/piecewise_ramp.py)

Read [](file:///Users/kaiarseneau/Documents/GitHub/CVT-Simulator/cvtModel/src/cvt_simulator/models/ramps/generate_sample_ramps.py#1-1), lines 1 to 100

Read [](file:///Users/kaiarseneau/Documents/GitHub/CVT-Simulator/cvtModel/src/cvt_simulator/models/ramps/linear_segment.py)

Read [](file:///Users/kaiarseneau/Documents/GitHub/CVT-Simulator/cvtModel/src/cvt_simulator/models/ramps/circular_segment.py)

Read [](file:///Users/kaiarseneau/Documents/GitHub/CVT-Simulator/cvtModel/src/cvt_simulator/models/ramps/cubic_spiral_zero_k1.py#1-1), lines 1 to 100

Searched for regex `Input|input|form|Form` (`**/frontend/src/pages/**`), 20 results

Read [](file:///Users/kaiarseneau/Documents/GitHub/CVT-Simulator/frontend/src/pages)

Read [](file:///Users/kaiarseneau/Documents/GitHub/CVT-Simulator/frontend/src/pages/input/Input.tsx)

Read [](file:///Users/kaiarseneau/Documents/GitHub/CVT-Simulator/backend/app/api/endpoints.py)

Read [](file:///Users/kaiarseneau/Documents/GitHub/CVT-Simulator/backend/app/models/response_models.py)

Searched for regex `class SimulationArgs|def simulate_cvt_model` (`**/cvtModel/src/**/*.py`), 2 results

Read [](file:///Users/kaiarseneau/Documents/GitHub/CVT-Simulator/cvtModel/src/cvt_simulator/utils/simulation_args.py)

Searched for regex `ramp|Ramp|PiecewiseRamp` (`**/cvtModel/src/**/*.py`), 20 results

Read [](file:///Users/kaiarseneau/Documents/GitHub/CVT-Simulator/cvtModel/src/cvt_simulator/models/pulley/primary_pulley_flyweight.py#80-80), lines 80 to 150

Read [](file:///Users/kaiarseneau/Documents/GitHub/CVT-Simulator/cvtModel/src/cvt_simulator/main.py)

Read [](file:///Users/kaiarseneau/Documents/GitHub/CVT-Simulator/frontend/src/types/index.ts)

Read [](file:///Users/kaiarseneau/Documents/GitHub/CVT-Simulator/frontend/src/types/parameter.ts#1-1), lines 1 to 100

Read [](file:///Users/kaiarseneau/Documents/GitHub/CVT-Simulator/cvtModel/src/cvt_simulator/models/model_initializer.py)

Now let me check how ramps can be serialized and look at other segment types: 

Read [](file:///Users/kaiarseneau/Documents/GitHub/CVT-Simulator/cvtModel/src/cvt_simulator/models/ramps/euler_spiral_segment.py#1-1), lines 1 to 50

Read [](file:///Users/kaiarseneau/Documents/GitHub/CVT-Simulator/cvtModel/src/cvt_simulator/models/ramps/cubic_spiral_zero_zero.py#1-1), lines 1 to 50

Read [](file:///Users/kaiarseneau/Documents/GitHub/CVT-Simulator/cvtModel/src/cvt_simulator/models/ramps/pro_defined_segment.py)

Now let me check the frontend utilities to understand the API structure better: 

Read [](file:///Users/kaiarseneau/Documents/GitHub/CVT-Simulator/frontend/src/utils/api.ts)

Read [](file:///Users/kaiarseneau/Documents/GitHub/CVT-Simulator/frontend/src/utils/parameterMapping.ts)

Perfect! Now I have enough context. Let me create a comprehensive plan for implementing the custom ramp feature.

## **Comprehensive Plan: Custom Ramp Builder for CVT Simulator**

Based on my analysis of the codebase, here's a detailed plan to implement the custom ramp feature:

---

### **Current Architecture Understanding**

**Ramp System (Backend/cvtModel):**
- **Base class**: `RampSegment` - defines `x_start`, `x_end`, `height(x)`, `slope(x)`
- **Segment types**: `LinearSegment`, `CircularSegment`, `CubicSpiralZeroK1`, `CubicSpiralZeroZero`, `EulerSpiralSegment`, `ProDefinedSegment`
- **Piecewise builder**: `PiecewiseRamp` - chains segments together, automatically ensures continuity by setting `y_start` of each new segment
- **Current usage**: Hardcoded in `create_default_flyweight_ramp()`, passed to `PhysicalPrimaryPulley` constructor

**API Layer:**
- FastAPI endpoint at `/run` accepts `SimulationArgsInput` (partial model)
- Currently, ramp is NOT passed through API - it's hardcoded in `get_models()`
- `SimulationArgs` has `primary_ramp_geometry: float = 1.0` but this is unused

**Frontend:**
- Input page uses `ParameterAccordion` + `InputField` for all parameters
- Parameters defined in parameter.ts
- API mapping in parameterMapping.ts
- No current ramp visualization capability

---

### **Proposed Solution Architecture**

#### **Phase 1: Data Schema & Serialization**

**1.1 Define JSON Schema for Ramp Segments**
```python
# cvtModel/src/cvt_simulator/models/ramps/ramp_serialization.py

RampSegmentConfig = {
    "type": "linear" | "circular" | "cubic_spiral_zero_k1" | ...,
    "x_start": float,
    "x_end": float,
    "params": {
        # Segment-specific parameters
        # Linear: {"slope": float}
        # Circular: {"radius": float, "theta_start": float, "theta_end": float}
        # etc.
    }
}

PiecewiseRampConfig = {
    "segments": [RampSegmentConfig, ...]
}
```

**1.2 Add Serialization Methods**
- Add `to_dict()` method to each segment class
- Add `from_dict()` class method to reconstruct segments
- Add `PiecewiseRamp.to_json()` and `PiecewiseRamp.from_json()` methods

**1.3 Update SimulationArgs**
```python
@dataclass
class SimulationArgs:
    # ... existing fields ...
    primary_ramp_config: dict | None = None  # JSON-serializable ramp config
```

---

#### **Phase 2: Backend API Updates**

**2.1 Ramp Preview Endpoint**
```python
# backend/app/api/endpoints.py

@router.post("/ramp/preview")
def preview_ramp(config: PiecewiseRampConfig):
    """
    Generates preview data for a ramp configuration.
    Returns x/y coordinates for visualization.
    """
    ramp = PiecewiseRamp.from_json(config)
    x_points = np.linspace(0, ramp.segments[-1].x_end, 100)
    y_points = [ramp.height(x) for x in x_points]
    slopes = [ramp.slope(x) for x in x_points]
    
    return {
        "x": x_points.tolist(),
        "y": y_points.tolist(),
        "slopes": slopes.tolist()
    }
```

**2.2 Update model_initializer.py**
```python
def get_models(args: SimulationArgs):
    # ... existing code ...
    
    # Handle custom ramp if provided
    ramp = None
    if args.primary_ramp_config:
        ramp = PiecewiseRamp.from_json(args.primary_ramp_config)
    
    primary_pulley = PhysicalPrimaryPulley(
        # ... other params ...
        ramp=ramp  # Will use default if None
    )
```

**2.3 Update Pydantic Models**
```python
# backend/app/models/response_models.py
# Add RampSegmentInput, PiecewiseRampInput models
# Update SimulationArgsInput to include primary_ramp_config
```

---

#### **Phase 3: Frontend - Ramp Builder UI**

**3.1 Create Ramp Builder Component**
```tsx
// frontend/src/components/rampBuilder/RampBuilder.tsx

interface RampBuilderProps {
    segments: RampSegmentConfig[];
    onChange: (segments: RampSegmentConfig[]) => void;
}

// Features:
// - List of current segments (draggable for reordering)
// - Add segment button with type selector
// - Parameter inputs for each segment (conditional based on type)
// - Delete segment button
// - Visual preview (chart showing ramp profile)
```

**3.2 Segment Type Selector**
```tsx
// Dropdown with options:
// - Linear (params: slope)
// - Circular (params: radius, theta_start, theta_end)
// - Cubic Spiral (Zero-K1) (params: slope_start, slope_end, target_curvature)
// - Cubic Spiral (Zero-Zero) (params: slope_start, slope_end)
// - Euler Spiral (params: slope_start, slope_end)
// - Pro Defined (params: prev_seg_height, end_length, initial_slope, r_initial)
```

**3.3 Segment Configuration Panel**
```tsx
// For each segment, show:
// - Segment number/name
// - Type dropdown
// - x_start, x_end inputs
// - Type-specific parameter inputs
// - Delete button
```

**3.4 Ramp Preview Chart**
```tsx
// Using existing charting library (looks like you use some chart lib)
// Real-time preview:
// - Call /ramp/preview endpoint on segment changes
// - Debounce API calls (500ms delay)
// - Show height vs x position
// - Optionally show slope overlay
```

**3.5 Integration into Input Page**
```tsx
// Add new parameter group: 'ramp' (or nest under 'primary')
// Add RampBuilder as a special input type
// Store ramp config in parameter state
// Map to API in parameterMapping.ts
```

---

#### **Phase 4: Frontend Type Definitions**

**4.1 Update parameter.ts**
```typescript
export type Parameter = 
  | /* existing params */
  | 'PrimaryRampConfig';

// Add to PARAMETERS:
PrimaryRampConfig: {
    label: 'Custom Ramp',
    description: 'Design a custom flyweight ramp profile...',
    type: 'ramp', // New type
    defaultValue: null, // Use default ramp if null
    validate: validators.rampConfig,
    units: '-',
    group: 'primary',
    img: primaryCVT,
}
```

**4.2 Create Ramp Types**
```typescript
// frontend/src/types/ramp.ts

export type RampSegmentType = 
  | 'linear' 
  | 'circular' 
  | 'cubic_spiral_zero_k1'
  | 'cubic_spiral_zero_zero'
  | 'euler_spiral'
  | 'pro_defined';

export interface BaseRampSegment {
    type: RampSegmentType;
    x_start: number;
    x_end: number;
}

export interface LinearSegment extends BaseRampSegment {
    type: 'linear';
    params: { slope: number };
}

// ... define other segment interfaces

export type RampSegmentConfig = 
  | LinearSegment 
  | CircularSegment 
  | /* ... */;

export interface PiecewiseRampConfig {
    segments: RampSegmentConfig[];
}
```

---

#### **Phase 5: User Experience Enhancements**

**5.1 Presets**
- Add "Load Preset" button with common ramp profiles
- "Default Ramp" preset matching current hardcoded ramp
- Save/load custom presets to local storage

**5.2 Validation**
- Ensure segments are continuous (x_end of segment N = x_start of segment N+1)
- Validate parameter ranges
- Show error messages for invalid configurations
- Disable "Run" button if ramp is invalid

**5.3 Visual Feedback**
- Highlight segment being edited in preview chart
- Show continuity indicators (dots at segment junctions)
- Display calculated properties (total length, max/min slope)

**5.4 Documentation**
- Add tooltip help for each segment type
- Link to documentation/images showing what each segment does
- Formula display for advanced users

---

### **Implementation Order**

1. **Backend First (minimal frontend)**
   - Add serialization to ramp classes (Phase 1.2)
   - Add `/ramp/preview` endpoint (Phase 2.1)
   - Test with curl/Postman

2. **Backend Integration**
   - Update SimulationArgs (Phase 1.3)
   - Update model_initializer (Phase 2.2)
   - Update Pydantic models (Phase 2.3)
   - Test full simulation with custom ramp

3. **Frontend - Basic Builder**
   - Create RampBuilder component (Phase 3.1)
   - Implement segment list UI (Phase 3.2, 3.3)
   - Wire up to parameter context

4. **Frontend - Preview**
   - Implement preview chart (Phase 3.4)
   - Connect to `/ramp/preview` API
   - Add debouncing

5. **Polish**
   - Add presets (Phase 5.1)
   - Add validation (Phase 5.2)
   - Add visual enhancements (Phase 5.3)
   - Add documentation (Phase 5.4)

---

### **Key Design Decisions**

✅ **Use JSON for serialization** - Easy to send over API, human-readable, easily extensible

✅ **Separate preview endpoint** - Keeps `/run` fast, allows real-time preview without running full simulation

✅ **Continuity handled by PiecewiseRamp** - Frontend only needs to specify x_start/x_end, backend auto-connects heights

✅ **Fallback to default** - If `primary_ramp_config` is null, use existing default ramp (no breaking changes)

✅ **Segment-specific params** - Each segment type has its own parameter object, making it extensible

✅ **Debounced preview** - Reduces API calls while user is actively editing

---

### **Challenges & Solutions**

| Challenge | Solution |
|-----------|----------|
| Complex parameter inputs | Conditional rendering based on segment type |
| Real-time preview performance | Debounce API calls, consider client-side calculation for simple segments |
| Validation across segments | Backend validates continuity, frontend shows errors |
| Large payload size | Minimal - JSON ramp config is small (~few KB) |
| Learning curve for users | Presets, tooltips, visual feedback, good defaults |

---

This plan provides a scalable, maintainable solution that:
- ✅ Allows piecewise construction matching your existing architecture
- ✅ Provides real-time visual feedback
- ✅ Passes cleanly through API without being cumbersome
- ✅ Works in simulation without major refactoring
- ✅ Is extensible to new segment types

Would you like me to start implementing any specific phase of this plan?