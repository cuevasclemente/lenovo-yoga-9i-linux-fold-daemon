#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""
Lenovo Yoga fold daemon using the Intel ISH IIO hinge-angle sensor.

The daemon reads the kernel IIO `hinge` sensor and inhibits the internal
keyboard/touchpad while the display is folded beyond a configurable threshold.
It intentionally does not read the Lenovo YMC SW_TABLET_MODE evdev switch,
because on some Yoga 9i Aura / Yoga 9 2-in-1 14ILL10 machines that switch can
stick in tablet mode and leave internal input disabled.
"""
from __future__ import annotations

import argparse
import glob
import signal
import sys
import time
from pathlib import Path

DEFAULT_DISABLE_ANGLE = 200.0
DEFAULT_ENABLE_ANGLE = 170.0
DEFAULT_POLL_SECONDS = 0.25
DEFAULT_TARGETS = ['AT Translated Set 2 keyboard', 'Touchpad']


def read_text(path: Path) -> str:
    return path.read_text(errors='replace').strip()


def find_iio_device_by_name(name: str) -> Path:
    for dev in sorted(Path('/sys/bus/iio/devices').glob('iio:device*')):
        name_file = dev / 'name'
        if name_file.exists() and read_text(name_file) == name:
            return dev
    raise FileNotFoundError(f'could not find IIO device named {name!r}')


def find_hinge_angle_file(configured: str | None) -> Path:
    if configured:
        p = Path(configured)
        if p.exists():
            return p
        raise FileNotFoundError(f'configured hinge angle file does not exist: {p}')

    hinge = find_iio_device_by_name('hinge')
    angle = hinge / 'in_angl0_raw'
    label = hinge / 'in_angl0_label'
    if not angle.exists():
        raise FileNotFoundError(f'hinge device exists but lacks {angle.name}: {hinge}')
    if label.exists() and read_text(label) != 'hinge':
        raise RuntimeError(f'{angle} is not labelled hinge; {label}={read_text(label)!r}')
    return angle


def read_angle_degrees(angle_file: Path) -> float:
    raw = read_text(angle_file)
    try:
        return float(raw)
    except ValueError as exc:
        raise RuntimeError(f'could not parse hinge angle from {angle_file}: {raw!r}') from exc


def target_input_dirs(name_needles: list[str]) -> list[Path]:
    targets: list[Path] = []
    for input_dir_s in glob.glob('/sys/class/input/input*'):
        input_dir = Path(input_dir_s)
        name_file = input_dir / 'name'
        inhibited_file = input_dir / 'inhibited'
        if not name_file.exists() or not inhibited_file.exists():
            continue
        name = read_text(name_file)
        if any(needle.lower() in name.lower() for needle in name_needles):
            targets.append(input_dir)
    return sorted(targets, key=lambda p: p.name)


def set_inhibited(targets: list[Path], inhibited: bool, dry_run: bool = False) -> None:
    value = '1' if inhibited else '0'
    verb = 'inhibit' if inhibited else 'enable '
    for input_dir in targets:
        name = read_text(input_dir / 'name')
        dest = input_dir / 'inhibited'
        print(f'{verb} {input_dir.name}: {name}', flush=True)
        if not dry_run:
            dest.write_text(value)


def main() -> int:
    ap = argparse.ArgumentParser(description='Inhibit Yoga internal input by ISH hinge angle')
    ap.add_argument('--angle-file', help='path to hinge angle raw file; defaults to IIO device named hinge')
    ap.add_argument('--disable-angle', type=float, default=DEFAULT_DISABLE_ANGLE,
                    help=f'disable input at or above this hinge angle, default {DEFAULT_DISABLE_ANGLE}')
    ap.add_argument('--enable-angle', type=float, default=DEFAULT_ENABLE_ANGLE,
                    help=f're-enable input at or below this hinge angle, default {DEFAULT_ENABLE_ANGLE}')
    ap.add_argument('--poll-seconds', type=float, default=DEFAULT_POLL_SECONDS)
    ap.add_argument('--target', action='append', default=[],
                    help='case-insensitive substring of input device name to inhibit; repeatable')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    if args.enable_angle >= args.disable_angle:
        print('enable-angle must be less than disable-angle for hysteresis', file=sys.stderr)
        return 2

    needles = args.target or DEFAULT_TARGETS
    targets = target_input_dirs(needles)
    if not targets:
        print(f'No target input devices found for: {needles}', file=sys.stderr)
        return 2

    try:
        angle_file = find_hinge_angle_file(args.angle_file)
    except Exception as exc:
        print(f'Hinge sensor unavailable: {exc}', file=sys.stderr)
        set_inhibited(targets, False, args.dry_run)
        return 2

    print(f'angle_file: {angle_file} -> {angle_file.resolve()}', flush=True)
    print(f'hysteresis: inhibit >= {args.disable_angle:.1f}°, enable <= {args.enable_angle:.1f}°', flush=True)
    print('targets: ' + ', '.join(f'{p.name}={read_text(p / "name")}' for p in targets), flush=True)

    stop = False

    def handle_stop(signum, frame):  # noqa: ARG001
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)

    inhibited = False
    last_printed_angle: float | None = None

    try:
        while not stop:
            try:
                angle = read_angle_degrees(angle_file)
            except Exception as exc:
                print(f'Error reading hinge angle; failsafe enabling targets: {exc}', file=sys.stderr, flush=True)
                set_inhibited(targets, False, args.dry_run)
                inhibited = False
                time.sleep(args.poll_seconds)
                continue

            if not inhibited and angle >= args.disable_angle:
                print(f'hinge angle {angle:.1f}° >= {args.disable_angle:.1f}°', flush=True)
                set_inhibited(targets, True, args.dry_run)
                inhibited = True
            elif inhibited and angle <= args.enable_angle:
                print(f'hinge angle {angle:.1f}° <= {args.enable_angle:.1f}°', flush=True)
                set_inhibited(targets, False, args.dry_run)
                inhibited = False
            elif last_printed_angle is None or abs(angle - last_printed_angle) >= 10:
                print(f'hinge angle {angle:.1f}°; inhibited={inhibited}', flush=True)
                last_printed_angle = angle

            time.sleep(args.poll_seconds)
    finally:
        # Failsafe: re-enable devices if the daemon is stopped/restarted.
        set_inhibited(targets, False, args.dry_run)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
