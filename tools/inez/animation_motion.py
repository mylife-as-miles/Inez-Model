"""Coordinate-explicit gait planning; no Blender/model mutation.

Inez faces Blender -Y, with +Z up and +X to her left. glTF export converts
this to +Z forward / +Y up. The in-place stance phase moves backwards at a
constant velocity; the viewer supplies the matching forward translation.
"""
from dataclasses import dataclass, asdict
import argparse
import json
import math
from pathlib import Path


def clamp(value, lower=0.0, upper=1.0):
    return max(lower, min(upper, value))


def ease(value):
    x = clamp(value)
    return x*x*(3.0-2.0*x)


def hermite(start, end, start_tangent, end_tangent, phase):
    t = clamp(phase)
    return ((2*t**3-3*t*t+1)*start + (t**3-2*t*t+t)*start_tangent
            + (-2*t**3+3*t*t)*end + (t**3-t*t)*end_tangent)


@dataclass(frozen=True)
class Gait:
    name: str
    duration: float
    stance_fraction: float
    speed: float
    clearance: float
    arm_swing_deg: float
    elbow_bend_deg: float
    forward_lean_deg: float
    lateral_sway: float
    vertical_bob: float
    height: float = 1.68

    @property
    def scale(self):
        return self.height/1.68

    @property
    def stride(self):
        return self.speed*self.duration*self.stance_fraction


def gait_specs(height=1.68):
    scale = height/1.68
    return {
        'Idle': Gait('Idle', 4.0, 1.0, 0.0, 0.0, 0.0, 13.0,
                     0.0, 0.003*scale, 0.0015*scale, height),
        'Walk': Gait('Walk', 1.14, 0.62, 0.95*scale, 0.065*scale,
                     21.0, 19.0, 2.0, 0.010*scale, 0.010*scale, height),
        'Run': Gait('Run', 0.76, 0.42, 2.65*scale, 0.105*scale,
                    34.0, 63.0, 8.0, 0.006*scale, 0.026*scale, height),
    }


def foot_cycle(gait, phase):
    """Return ankle horizontal travel, sole lift and sagittal boot pitch.

    Hermite swing tangents match the stance velocity at toe-off/landing.
    Foot lift has zero vertical velocity at these contacts. Sole lift is
    measured from the boot's rotated lower surface, not the ankle joint.
    """
    p = phase % 1.0
    if gait.name == 'Idle':
        return {'y': 0.0, 'lift': 0.0, 'pitch': 0.0,
                'contact': True, 'phase': p, 'swing_phase': None}
    stride = gait.stride
    stance = gait.stance_fraction
    if p < stance:
        q = p/stance
        y = -stride*0.5 + stride*q
        heel_angle = math.radians(-5.0 if gait.name == 'Walk' else -3.0)
        toe_angle = math.radians(12.0 if gait.name == 'Walk' else 15.0)
        if q < 0.18:
            pitch = heel_angle*(1.0-ease(q/0.18))
        elif q > 0.77:
            pitch = toe_angle*ease((q-0.77)/0.23)
        else:
            pitch = 0.0
        return {'y': y, 'lift': 0.0, 'pitch': pitch,
                'contact': True, 'phase': p, 'swing_phase': None}
    q = (p-stance)/(1.0-stance)
    tangent = stride*(1.0-stance)/stance
    y = hermite(stride*0.5, -stride*0.5, tangent, tangent, q)
    lift = gait.clearance*math.sin(math.pi*q)**2
    toe_angle = math.radians(12.0 if gait.name == 'Walk' else 15.0)
    heel_angle = math.radians(-5.0 if gait.name == 'Walk' else -3.0)
    if q < 0.45:
        pitch = toe_angle + (math.radians(-9.0)-toe_angle)*ease(q/0.45)
    else:
        pitch = math.radians(-9.0)+(heel_angle-math.radians(-9.0))*ease((q-0.45)/0.55)
    return {'y': y, 'lift': lift, 'pitch': pitch,
            'contact': False, 'phase': p, 'swing_phase': q}


def arm_cycle(gait, phase, side):
    """Sagittal upper/forearm angles in radians; arms oppose the legs."""
    p = phase % 1.0
    if gait.name == 'Idle':
        upper = math.radians(2.0) + math.radians(0.6)*math.sin(2*math.pi*p)
        elbow = math.radians(gait.elbow_bend_deg)
    else:
        # At left heel contact, the left arm reaches backwards.
        phase_offset = 0.0 if side == 'L' else 0.5
        upper = math.radians(gait.arm_swing_deg)*math.cos(2*math.pi*(p+phase_offset))
        elbow = math.radians(gait.elbow_bend_deg)
        elbow += math.radians(4.0 if gait.name == 'Run' else 2.0)*math.sin(2*math.pi*(p+phase_offset))
    return upper, upper-elbow


def mathematical_report(height=1.68):
    result = {'status': 'prepared gait curves only; model deformation not yet tested',
              'axes': {'up': '+Z', 'forward': '-Y'}, 'clips': {}}
    for name, gait in gait_specs(height).items():
        samples = [foot_cycle(gait, i/1000) for i in range(1001)]
        endpoints = [foot_cycle(gait, 0), foot_cycle(gait, 1)]
        report = asdict(gait)
        report.update({'stride_m': gait.stride,
                       'ankle_y_range_m': [min(s['y'] for s in samples), max(s['y'] for s in samples)],
                       'maximum_sole_lift_m': max(s['lift'] for s in samples),
                       'cycle_endpoint_position_error_m': abs(endpoints[0]['y']-endpoints[1]['y']),
                       'cycle_endpoint_pitch_error_rad': abs(endpoints[0]['pitch']-endpoints[1]['pitch']),
                       'stance_speed_m_s': gait.speed,
                       'is_in_place': True})
        result['clips'][name] = report
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--height', type=float, default=1.68)
    parser.add_argument('--report')
    args = parser.parse_args()
    report = mathematical_report(args.height)
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))
