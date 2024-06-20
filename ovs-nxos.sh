#!/bin/bash

# This script is part of https://inetdoc.net project
#
# It starts a qemu/kvm x86 Nexus 9000v swicth which ports are plugged to Open
# vSwitch ports through already existing tap interfaces named nxtapXXX.
#
# This script should be run by a normal user account which belongs to the kvm
# system group and is able to run the ovs-vsctl command via sudo.
#
# Nexus to OvS port mapping is given by a yaml description file which is
# parsed with the yq command.
# Yaml example file:
#
#	switch:
#	  hostname: sw0
#	  instnum: 1
#	  mgmt0: 10
#	  ethernet:
#	    - 231
#	    - 232
#	    - 233
#	    - 234
#
# File: ovs-nxos.sh
# Author: Philippe Latu
# Source: https://gitlab.inetdoc.net/labs/startup-scripts
#
#	This program is free software: you can redistribute it and/or modify
#	it under the terms of the GNU General Public License as published by
#	the Free Software Foundation, either version 3 of the License, or
#	(at your option) any later version.
#
#	This program is distributed in the hope that it will be useful,
#	but WITHOUT ANY WARRANTY; without even the implied warranty of
#	MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#	GNU General Public License for more details.
#
#	You should have received a copy of the GNU General Public License
#	along with this program.  If not, see <http://www.gnu.org/licenses/>.

RED='\e[1;31m'
GREEN='\e[1;32m'
BLUE='\e[1;34m'
NC='\e[0m' # No Color

vm="$1"
image_format="${vm##*.}"
shift
yamlfile="$1"
shift

# Are the 2 parameters there ?
if [[ -z ${vm} || -z ${yamlfile} ]]; then
	echo -e "${RED}ERROR : missing parameter.${NC}"
	echo -e "${GREEN}Usage : $0 [image file] [port list yaml file]${NC}"
	exit 1
fi

# Does the VM image file exist ?
if [[ ! -f ${vm} ]]; then
	echo -e "${RED}ERROR : the ${vm} image file does not exist.${NC}"
	exit 1
fi

# Is the VM image file already in use ?
if pgrep -u "${USER}" -l -f "\-name\ ${vm}"; then
	echo -e "${RED}ERROR : the ${vm} image file is in use.${NC}"
	exit 1
fi

# Is 'yq' command available ?
if ! command -v yq &>/dev/null; then
	echo -e "${RED}~> yq command is not available.${NC}"
	echo -e "${GREEN}Install it with: sudo apt install yq${NC}"
	tput sgr0
	exit 1
fi

# OOB port mgmt0
tap_mgmt=$(yq .switch.mgmt0 <"${yamlfile}")
spice=$((9900 + tap_mgmt))
telnet=$((9000 + tap_mgmt))

# Is the mgmt0 OOB interface mapped to a free tap interface ?
if [[ -n "$(pgrep -f "=[n]xtap${tap_mgmt}," || true)" ]]; then
	echo -e "${RED}Interface nxtap${tap_mgmt} is already in use.${NC}"
	exit 1
fi

hostName=$(yq .switch.hostname <"${yamlfile}" | tr -d '"' || true)
instNum=$(yq .switch.instnum <"${yamlfile}")
ports=$(yq .switch.ethernet <"${yamlfile}" | tr -d '[], ' | sed '/^$/d' || true)
mapfile -t tapList <<<"${ports}"
tapNum=${#tapList[@]}
tapNum=$((tapNum - 1))
ethPorts=""

# Are the Ethernet interfaces mapped to free tap interfaces ?
for i in $(seq 0 "${tapNum}"); do
	if [[ -n "$(pgrep -f "=[n]xtap${tapList[${i}]}," || true)" ]]; then
		echo -e "${RED}Interface nxtap${tapList[${i}]} is already in use.${NC}"
		exit 1
	fi
done

# The OUI part of the Ethernet ports MAC address is chosen to build IPv6 Link Local address
oui=(00 30 24)
oui_mac="${oui[0]}:${oui[1]}:${oui[2]}"

# The last 2 bytes of MAC address are generated from mgmt0 port
# tap interface number
second_rightmost_byte=$(printf "%02x" $((tap_mgmt / 256)))
rightmost_byte=$(printf "%02x" $((tap_mgmt % 256)))

# mgmt addressing
mgmt_mac="${oui_mac}:ae:${second_rightmost_byte}:${rightmost_byte}"
ll_id="$(printf '%x' "${tap_mgmt}")"
lladdress="fe80::$((oui[0] + 2))${oui[1]}:${oui[2]}ff:feae:${ll_id}"
svi="vlan$(sudo ovs-vsctl get port "tap${tap_mgmt}" tag)"

for i in $(seq 0 "${tapNum}"); do
	addr=$((i + 1))
	ethPorts+="-netdev tap,ifname=nxtap${tapList[${i}]},script=no,downscript=no,id=eth1_1_${addr} \
		-device e1000,bus=bridge-1,addr="1.${addr}",netdev="eth1_1_${addr}",mac=${oui_mac}:01:$(printf '%02x' "${instNum}"):$(printf '%02x' "${addr}"),multifunction=on,romfile= "
done

# RAM size
memory=12288

# Are the OVMF symlink and file copy there ?
if [[ ! -L "./OVMF_CODE.fd" ]]; then
	ln -s /usr/share/OVMF/OVMF_CODE_4M.fd ./OVMF_CODE.fd
fi

if [[ ! -f "${vm}_OVMF_VARS.fd" ]]; then
	cp /usr/share/OVMF/OVMF_VARS_4M.fd "${vm}_OVMF_VARS.fd"
fi

echo -e "${RED}---${NC}"
echo -e "~> Switch name                : ${RED}${hostName}${NC}"
echo -e "~> RAM size                   : ${RED}${memory}MB${NC}"
echo -e "~> SPICE VDI port number      : ${GREEN}${spice}${NC}"
echo -e "~> telnet console port number : ${GREEN}${telnet}${NC}"
echo -ne "~> mgmt0 tap interface        : ${BLUE}nxtap${tap_mgmt}"
echo -e ", $(sudo ovs-vsctl get port "nxtap${tap_mgmt}" vlan_mode || true) mode${NC}"
echo -e "~> mgmt0 IPv6 LL address      : ${BLUE}${lladdress}%${svi}${NC}"
for i in $(seq 0 "${tapNum}"); do
	echo -ne "~> Ethernet1/"$((i + 1))" tap interface  : ${BLUE}nxtap${tapList[${i}]}"
	echo -e ", $(sudo ovs-vsctl get port "nxtap${tapList[${i}]}" vlan_mode || true) mode${NC}"
done
tput sgr0

# shellcheck disable=SC2086
ionice -c3 nohup qemu-system-x86_64 \
	-machine type=q35,smm=on,accel=kvm,kernel-irqchip=split \
	-cpu max,l3-cache=on,+vmx,pcid=on,spec-ctrl=on,stibp=on,ssbd=on,pdpe1gb=on,md-clear=on,vme=on,f16c=on,rdrand=on,tsc_adjust=on,xsaveopt=on,hypervisor=on,arat=off,abm=on \
	-device intel-iommu,intremap=on \
	-smp cpus=4 \
	-daemonize \
	-m "${memory}" \
	-global ICH9-LPC.disable_s3=1 \
	-global ICH9-LPC.disable_s4=1 \
	--device virtio-balloon \
	-rtc base=localtime,clock=host \
	-device i6300esb \
	-watchdog-action poweroff \
	-global driver=cfi.pflash01,property=secure,value=on \
	-drive if=pflash,format=raw,unit=0,file=OVMF_CODE.fd,readonly=on \
	-drive if=pflash,format=raw,unit=1,file="${vm}_OVMF_VARS.fd" \
	-k fr \
	-vga none \
	-device qxl-vga,vgamem_mb=64 \
	-spice port="${spice}",addr=localhost,disable-ticketing=on \
	-device virtio-serial-pci \
	-device virtserialport,chardev=spicechannel0,name=com.redhat.spice.0 \
	-chardev spicevmc,id=spicechannel0,name=vdagent \
	-object rng-random,filename=/dev/urandom,id=rng0 \
	-device virtio-rng-pci,rng=rng0 \
	-device i82801b11-bridge,id=dmi-pci-bridge \
	-device pci-bridge,id=bridge-1,chassis_nr=1,bus=dmi-pci-bridge \
	-device pci-bridge,id=bridge-2,chassis_nr=2,bus=dmi-pci-bridge \
	-device pci-bridge,id=bridge-3,chassis_nr=3,bus=dmi-pci-bridge \
	-device pci-bridge,id=bridge-4,chassis_nr=4,bus=dmi-pci-bridge \
	-device ahci,id=ahci0 \
	-drive file="${vm}",if=none,id=drive-sata-disk0,format="${image_format}",media=disk \
	-device ide-hd,bus=ahci0.0,drive=drive-sata-disk0,id=drive-sata-disk0,bootindex=1 \
	-device virtio-serial-pci \
	-usb \
	-device usb-tablet,bus=usb-bus.0 \
	-serial telnet:localhost:"${telnet}",server,nowait \
	-netdev tap,ifname="nxtap${tap_mgmt}",script=no,downscript=no,id=mgmt0 \
	-device e1000,bus=bridge-1,addr=1.0,netdev=mgmt0,mac="${mgmt_mac}",multifunction=on,romfile= \
	${ethPorts} >"${vm}.out" 2>&1
