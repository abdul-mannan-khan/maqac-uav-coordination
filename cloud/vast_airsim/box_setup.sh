#!/bin/bash
# Runs ON the Vast box. Installs Wine 11.0 + DXVK 3.1.1,
# AirSim 1.8.1 CityEnviron (Windows build, from the official GitHub release), PX4 v1.14.3 SITL, Python deps.
# Log: /root/setup.log; writes /root/SETUP_DONE when finished. No project data needed.
set -x
export DEBIAN_FRONTEND=noninteractive
cd /root
apt-get update -qq
apt-get install -y -qq wget curl git unzip p7zip-full xvfb xauth x11-utils mesa-utils vulkan-tools libvulkan1 \
   python3 python3-pip python3-venv software-properties-common gnupg2 lsb-release sudo tmux rsync >/dev/null
# Vulkan ICD for the NVIDIA libraries mounted by the container runtime
mkdir -p /usr/share/vulkan/icd.d
echo '{"file_format_version":"1.0.0","ICD":{"library_path":"libEGL_nvidia.so.0","api_version":"1.3.0"}}' > /usr/share/vulkan/icd.d/nvidia_icd.json
# WineHQ stable, pinned to 11.0
dpkg --add-architecture i386
mkdir -pm755 /etc/apt/keyrings
wget -qO /etc/apt/keyrings/winehq-archive.key https://dl.winehq.org/wine-builds/winehq.key
wget -qNP /etc/apt/sources.list.d/ https://dl.winehq.org/wine-builds/ubuntu/dists/$(lsb_release -cs)/winehq-$(lsb_release -cs).sources
WV=11.0.0.0~jammy-1   # validated 6-7 Nov 2026 (winehq-stable moves on; pin it)
apt-get update -qq && apt-get install -y -qq --install-recommends winehq-stable=$WV wine-stable=$WV wine-stable-amd64=$WV wine-stable-i386=$WV >/dev/null
wine --version
# CityEnviron (official release v1.8.1-windows)
mkdir -p /opt/city && cd /opt/city
for p in 001 002; do wget -q https://github.com/microsoft/AirSim/releases/download/v1.8.1-windows/CityEnviron.zip.$p; done
cat CityEnviron.zip.001 CityEnviron.zip.002 > CityEnviron.zip && rm CityEnviron.zip.00? && (unzip -q CityEnviron.zip || 7z x -y CityEnviron.zip >/dev/null) && rm CityEnviron.zip
find /opt/city -path "*Binaries/Win64/CityEnviron.exe" | head -1 > /root/city_exe.txt   # the real binary, not the bootstrap
cat /root/city_exe.txt
# Wine prefix + DXVK 2.3.1
export WINEPREFIX=/root/wine_city WINEDEBUG=-all VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/nvidia_icd.json XDG_RUNTIME_DIR=/tmp
export WINEDLLOVERRIDES='mscoree,mshtml='   # skip the Mono/Gecko install dialogs (they hang on a headless display)
Xvfb :99 -screen 0 1280x720x24 >/dev/null 2>&1 & XP=$!; export DISPLAY=:99
wineboot -i >/dev/null 2>&1; wineserver -w
cd /root && wget -q https://github.com/doitsujin/dxvk/releases/download/v3.1.1/dxvk-3.1.1.tar.gz && tar xzf dxvk-3.1.1.tar.gz   # 2.3.1 hangs in vkCreateDevice on NVIDIA 595 (6 Nov)
for d in d3d11 dxgi d3d10core d3d9; do
  cp dxvk-3.1.1/x64/$d.dll $WINEPREFIX/drive_c/windows/system32/
  cp dxvk-3.1.1/x32/$d.dll $WINEPREFIX/drive_c/windows/syswow64/
  wine reg add 'HKEY_CURRENT_USER\Software\Wine\DllOverrides' /v $d /d native /f >/dev/null 2>&1
done
wineserver -w; kill $XP
# PX4 v1.14.3 SITL (same version as the GCP container)
cd /opt && git clone -q --depth 1 --branch v1.14.3 --recursive --shallow-submodules https://github.com/PX4/PX4-Autopilot.git
cd /opt/PX4-Autopilot && bash Tools/setup/ubuntu.sh --no-nuttx --no-sim-tools >/root/px4_deps.log 2>&1
pip3 install -q 'empy==3.3.4'                      # PX4 1.14 templates break with empy 4
git config --global --add safe.directory '*'
(cd platforms/nuttx/NuttX/nuttx && git tag -f nuttx-11.0.0)   # shallow clone drops the tag the version script needs
DONT_RUN=1 make px4_sitl_default -j$(nproc) >/root/px4_build.log 2>&1; ls -la build/px4_sitl_default/bin/px4
# Python for the bridge
pip3 install -q numpy scipy pillow pymavlink msgpack-rpc-python && pip3 install -q --no-deps airsim
python3 -c "import airsim, pymavlink, scipy; print('py deps ok')"
touch /root/SETUP_DONE
