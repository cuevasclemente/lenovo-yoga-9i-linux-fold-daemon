# Lenovo Yoga 9i Linux fold daemon

A small Linux daemon for the Lenovo Yoga 9i Aura / Yoga 9 2-in-1 14ILL10 that disables the internal keyboard and touchpad when the screen is folded back, then re-enables them when unfolded.

It uses the Intel ISH **IIO hinge sensor** (`/sys/bus/iio/devices/.../in_angl0_raw`) instead of Lenovo's `lenovo_ymc` tablet-mode switch.

## Authorship and attribution

This project was co-authored by:

- **Clemente Cuevas**
- **GPT 5.5 on Pi**

Sources and references consulted while debugging and building this:

- [`johnmeade/linux-yoga-9i-2-in-1-aura`](https://github.com/johnmeade/linux-yoga-9i-2-in-1-aura) — primary Yoga 9i Aura Linux compatibility notes and ISH firmware workaround.
- Lenovo support page for **Intel Integrated Sensor Hub Driver for Windows 11 (64-bit) - Yoga 9 2-in-1 14ILL10** (`DS572874`, package `zzyo037fue80ujh0.exe`) — source of the Windows firmware package used to extract `ishS_MEU_aligned.bin`.
- [`dnsense.pub` Samsung Book 5 sensor-hub post](https://dnsense.pub/posts/9-book5-sensor-hub/) — referenced by the Yoga 9i Aura guide for the general ISH firmware-copy approach.
- Linux kernel `lenovo_ymc` / Yoga Tablet Mode Control driver discussions and metadata — used to understand the `SW_TABLET_MODE` path that was sticking on this machine.
- Linux kernel `hid-sensor-custom-intel-hinge` / HID Hinge driver metadata — used to understand the IIO hinge angle channels exposed after ISH firmware loaded.
- Fedora and CachyOS community reports about Yoga 9i / Yoga 9i Aura tablet mode getting stuck — used to confirm this was a broader Linux behavior pattern, not just a local configuration issue.

## Why this exists

On our Yoga 9 2-in-1 14ILL10 (`83LC`) under CachyOS, the upstream `lenovo_ymc` driver exposed a `Lenovo Yoga Tablet Mode Control switch` / `SW_TABLET_MODE` device. It looked promising, but was unsafe on this machine:

- it only fired near a full 360° fold,
- it could remain stuck in tablet mode after unfolding,
- internal keyboard/touchpad could remain disabled even at the LUKS prompt or from a LiveUSB,
- live-reloading Lenovo platform modules disturbed other platform state such as Wi-Fi/rfkill.

The reliable path was:

1. install the Lenovo/Intel ISH firmware so Linux sees the real hinge and accelerometer sensors,
2. prevent `lenovo_ymc` from participating,
3. use the hinge angle directly and inhibit only the target input devices via sysfs.

With `lenovo_ymc` blacklisted, full 360° folding no longer locked us out, and this daemon re-enabled input correctly when unfolding.

## Hardware tested

- Lenovo product: `83LC`
- Model/version: `Yoga 9 2-in-1 14ILL10`
- Distro tested: CachyOS
- Working ISH firmware result:
  - `iio:device3 name=accel_3d`
  - `iio:device4 name=hinge`
- Internal keyboard target: `AT Translated Set 2 keyboard`
- Internal touchpad target: `CIRQ1080:00 0488:1054 Touchpad`

## Install ISH firmware first

The hinge sensor depends on proprietary Intel ISH firmware. Do **not** redistribute the firmware file; copy/extract it from your own Windows installation or Lenovo's official driver package.

The exact community guide we followed is:

- <https://github.com/johnmeade/linux-yoga-9i-2-in-1-aura>

### Option A: copy from Windows

If Windows is still installed, copy a file like:

```text
C:\Windows\System32\DriverStore\FileRepository\ishheciextensiontemplate.inf_amd64_[RANDOM]\FwImage\0003\ishS_MEU_aligned.bin
```

### Option B: extract Lenovo's driver

Download Lenovo's **Intel Integrated Sensor Hub Driver for Windows 11 (64-bit) - Yoga 9 2-in-1 14ILL10**. The Lenovo package we used was named:

```text
zzyo037fue80ujh0.exe
```

Extract with `innoextract`:

```sh
mkdir -p /tmp/yoga-ish-fw
cd /tmp/yoga-ish-fw
innoextract zzyo037fue80ujh0.exe
find . -iname ishS_MEU_aligned.bin
```

Install as the Linux firmware name expected by `intel_ish_ipc`:

```sh
sudo mkdir -p /lib/firmware/intel/ish
sudo cp -a /lib/firmware/intel/ish /lib/firmware/intel/ish.backup.$(date +%Y%m%d-%H%M%S)
sudo install -m 0644 ./code\$GetExtractPath\$/Source/IshHeciExtensionTemplate/x64/FWImage/0003/ishS_MEU_aligned.bin /lib/firmware/intel/ish/ish_lnlm.bin
```

Rebuild initramfs / boot entries. Examples:

```sh
# CachyOS / Limine setup used on the tested machine
sudo limine-mkinitcpio

# Arch-style alternative
sudo mkinitcpio -P

# Fedora alternative
sudo dracut --force
```

Reboot, then verify:

```sh
dmesg | grep -iE 'intel_ish|ish loader|hid-sensor'
for d in /sys/bus/iio/devices/iio:device*; do echo "$d $(cat "$d/name" 2>/dev/null)"; done
```

Expected success includes:

```text
ISH loader: firmware loaded. size:526848
FW base version: 5.8.0.7720
FW project version: 1.0.6.12644
iio:device... accel_3d
iio:device... hinge
```

## Disable `lenovo_ymc`

This daemon is intended to replace `lenovo_ymc` tablet-mode handling. Blacklist `lenovo_ymc` so the buggy/sticky `SW_TABLET_MODE` path is not used.

Recommended kernel command line parameters:

```text
module_blacklist=lenovo_ymc modprobe.blacklist=lenovo_ymc rd.driver.blacklist=lenovo_ymc
```

On the tested CachyOS/Limine system, these were added to `/etc/default/limine` next to the existing kernel command line, then regenerated with:

```sh
sudo limine-mkinitcpio
```

After reboot:

```sh
lsmod | grep '^lenovo_ymc' || echo 'lenovo_ymc not loaded'
tr ' ' '\n' < /proc/cmdline | grep lenovo_ymc
```

The Makefile also has a weaker modprobe-only helper:

```sh
sudo make install-modprobe-blacklist
```

Kernel-command-line blacklisting is still preferred, especially if your initramfs or early boot may load the module.

## Install the daemon

```sh
make check
sudo make install
sudo make enable
```

Useful commands:

```sh
sudo make status
sudo make logs
sudo make restart
sudo make disable
```

The service installs:

- `/usr/local/bin/yoga-fold-daemon`
- `/etc/systemd/system/yoga-fold-daemon.service`

## Defaults

The daemon defaults are:

```text
disable internal input when hinge angle >= 200°
re-enable internal input when hinge angle <= 170°
poll every 0.25 seconds
target devices containing:
  - AT Translated Set 2 keyboard
  - Touchpad
```

On the tested machine, the hinge angle was read from:

```text
/sys/bus/iio/devices/iio:device4/in_angl0_raw
```

The daemon discovers the `hinge` IIO device by name, so the `iio:deviceN` number may change across boots.

## Dry-run / calibration

Run without writing sysfs flags:

```sh
sudo /usr/local/bin/yoga-fold-daemon --dry-run
```

Fold slowly and watch logs. If you want different thresholds, edit the systemd unit `ExecStart` or run manually with flags:

```sh
sudo /usr/local/bin/yoga-fold-daemon --disable-angle 210 --enable-angle 175
```

The hysteresis is important: `--enable-angle` must be lower than `--disable-angle`, otherwise input can flap near the threshold.

## Safety and recovery

This daemon only writes each target input device's sysfs `inhibited` flag. It also re-enables targets on shutdown/restart as a failsafe.

Manual re-enable commands, adjusted to your event/input numbers:

```sh
for i in /sys/class/input/input*; do
  n=$(cat "$i/name" 2>/dev/null || true)
  case "$n" in
    *Touchpad*|*'AT Translated Set 2 keyboard'*) echo 0 | sudo tee "$i/inhibited" ;;
  esac
done
```

### EC drain / hard reset

The **EC** is the laptop's embedded controller: a small always-on microcontroller that manages platform hardware such as keyboard/touchpad state, power buttons, lid/fold signals, battery/charging, fans, and other low-level laptop behavior. It can keep state across normal reboots because parts of the machine remain powered from the battery or adapter.

If the old `lenovo_ymc`/EC tablet-mode path ever leaves internal input dead even outside Linux, the recovery that worked on the tested machine was an EC drain / hard reset:

1. shut the OS down completely,
2. after the laptop is off, keep holding the power button for about **60 additional seconds**,
3. unplug external power during the drain if possible,
4. release the power button,
5. plug power back in if desired and boot again.

This is not a normal reboot; the point is to force the EC to lose/reset the stale tablet-mode/input-disable state.

## Notes

- This does not implement screen rotation.
- If KDE/KWin has separately disabled the touchpad, check `~/.config/kcminputrc` and KWin input-device DBus state; that is separate from kernel sysfs inhibition.
- This project intentionally does not include or redistribute Lenovo/Intel firmware.
