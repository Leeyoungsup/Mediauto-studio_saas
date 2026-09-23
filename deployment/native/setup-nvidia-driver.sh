#!/usr/bin/env bash
set -euo pipefail
if [[ $EUID -ne 0 ]]; then exec sudo bash "$0" "$@"; fi
minimum=570.26
compatible=true
versions=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null) || compatible=false
[[ -n "$versions" ]] || compatible=false
while IFS= read -r version; do
  [[ "$version" =~ ^[0-9]+\.[0-9]+(\.[0-9]+)?$ ]] && dpkg --compare-versions "$version" ge "$minimum" || compatible=false
done <<< "$versions"
if $compatible; then echo 'NVIDIA driver is compatible; keeping it.'; exit 0; fi
if grep -qi microsoft /proc/sys/kernel/osrelease; then
  echo 'WSL uses the Windows host GPU driver. Update that driver on Windows and rerun setup; no Linux display driver will be installed.' >&2
  exit 1
fi
found=false
for device in /sys/bus/pci/devices/*; do
  if [[ $(cat "$device/vendor") == 0x10de && $(cat "$device/class") == 0x03* ]]; then found=true; break; fi
done
$found || { echo 'No NVIDIA display device found.' >&2; exit 1; }
source /etc/os-release
export DEBIAN_FRONTEND=noninteractive
apt-get update
case "$ID" in
  ubuntu)
    apt-get install -y ubuntu-drivers-common
    package=$(ubuntu-drivers devices | awk '$1=="driver" && /recommended/ {print $3; exit}')
    [[ "$package" =~ ^nvidia-driver-[0-9]+(-server)?(-open)?$ ]] || { echo 'No supported recommended NVIDIA package was found.' >&2; exit 1; }
    ;;
  debian) package=nvidia-driver ;;
  *) echo 'Automatic driver setup supports Ubuntu/Debian.' >&2; exit 1 ;;
esac
candidate=$(apt-cache policy "$package" | awk '/Candidate:/ {print $2; exit}')
if [[ -z "$candidate" || "$candidate" == '(none)' ]] || ! dpkg --compare-versions "${candidate#*:}" ge "$minimum"; then
  echo "The configured OS repositories do not offer a compatible GPU driver ($package: $candidate). Update the supported OS/repositories or install a supported NVIDIA driver, then retry." >&2
  exit 1
fi
echo "Installing distribution NVIDIA driver: $package ($candidate)"
apt-get install -y "linux-headers-$(uname -r)" "$package"
echo 'REBOOT REQUIRED: Restart Linux manually and rerun the same installer. If Secure Boot requests MOK enrollment, complete it during reboot. Setup will not reboot automatically.'
exit 20
