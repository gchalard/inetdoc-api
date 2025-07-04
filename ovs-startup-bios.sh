#!/bin/bash

# This script is part of https://inetdoc.net project
#
# It starts a qemu/kvm x86 virtual machine plugged into an Open VSwitch port
# through an already existing tap interface.  It should be run by a normal user
# account which belongs to the kvm system group and is able to run the
# ovs-vsctl command via sudo
#
# This version of the virtual machine startup script uses legacy BIOS.
#
# File: ovs-startup-bios.sh
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

vm=$1
shift
memory=$1
shift
tapnum=$1
shift

# Are the 3 parameters there ?
if [[ -z ${vm} || -z ${memory} || -z ${tapnum} ]]; then
	echo -e "${RED}ERROR : missing parameter.${NC}"
	echo -e "${GREEN}Usage : $0 [image file] [RAM size in MB] [tap interface number]${NC}"
	exit 1
fi

# Does the VM image file exist ?
if [[ ! -f ${vm} ]]; then
	echo -e "${RED}ERROR : the ${vm} image file does not exist.${NC}"
	exit 1
fi

# Is the VM image file already in use ?
user_vm="$(pgrep -u "${USER}" -l -f "\-name\ ${vm}")"
if [[ -n ${user_vm} ]]; then
	echo -e "${RED}ERROR : the ${vm} image file is in use.${NC}"
	exit 1
fi

# Is the amount of ram sufficient to run the VM ?
if [[ ${memory} -lt 128 ]]; then
	echo -e "${RED}ERROR : unsifficient RAM size : ${memory}MB${NC}"
	echo -e "${GREEN}RAM size must be above 128MB.${NC}"
	exit 1
fi

# Is the tap interface free ?
user_tap="$(pgrep -f "=[t]ap${tapnum},")"
if [[ -n ${user_tap} ]]; then
	echo -e "${RED}tap${tapnum} is already in use by another process.${NC}"
	exit 1
fi

# Is the switch port available ? Which mode ? Which VLAN ?
second_rightmost_byte=$(printf "%02x" $((tapnum / 256)))
rightmost_byte=$(printf "%02x" $((tapnum % 256)))
macaddress="b8:ad:ca:fe:${second_rightmost_byte}:${rightmost_byte}"
lladdress="fe80::baad:caff:fefe:$(printf "%x" "${tapnum}")"
vlan_mode="$(sudo ovs-vsctl get port "tap${tapnum}" vlan_mode)"

if [[ ${vlan_mode} == "access" ]]; then
	svi="vlan$(sudo ovs-vsctl get port "tap${tapnum}" tag)"
else
	svi="dsw-host"
fi

image_format="${vm##*.}"

spice=$((5900 + tapnum))
telnet=$((2300 + tapnum))

echo -e "~> Virtual machine filename   : ${RED}${vm}${NC}"
echo -e "~> RAM size                   : ${RED}${memory}MB${NC}"
echo -e "~> SPICE VDI port number      : ${GREEN}${spice}${NC}"
echo -e "~> telnet console port number : ${GREEN}${telnet}${NC}"
echo -e "~> MAC address                : ${BLUE}${macaddress}${NC}"
echo -e "~> Switch port interface      : ${BLUE}tap${tapnum}, ${vlan_mode} mode${NC}"
echo -e "~> IPv6 LL address            : ${BLUE}${lladdress}%${svi}${NC}"
tput sgr0

ionice -c3 nohup qemu-system-x86_64 \
	-machine type=q35,smm=on,accel=kvm:tcg,kernel-irqchip=split \
	-cpu max,l3-cache=on,+vmx,pcid=on,spec-ctrl=on,stibp=on,ssbd=on,pdpe1gb=on,md-clear=on,vme=on,f16c=on,rdrand=on,tsc_adjust=on,xsaveopt=on,hypervisor=on,arat=off,abm=on \
	-device intel-iommu,intremap=on \
	-smp cpus=4 \
	-daemonize \
	-name "${vm}" \
	-m "${memory}" \
	-global ICH9-LPC.disable_s3=1 \
	-global ICH9-LPC.disable_s4=1 \
	-device virtio-net-pci,mq=on,vectors=6,netdev=net"${tapnum}",disable-legacy=on,disable-modern=off,mac="${macaddress}",bus=pcie.0 \
	-netdev type=tap,queues=2,ifname=tap"${tapnum}",id=net"${tapnum}",script=no,downscript=no,vhost=on \
	-serial telnet:localhost:"${telnet}",server,nowait \
	-device virtio-balloon \
	-rtc base=localtime,clock=host \
	-device i6300esb \
	-watchdog-action poweroff \
	-boot order=c,menu=on \
	-drive if=none,id=drive0,format="${image_format}",media=disk,file="${vm}" \
	-device nvme,drive=drive0,serial=feedcafe \
	-k fr \
	-vga none \
	-device qxl-vga,vgamem_mb=64,vram64_size_mb=64,vram_size_mb=64 \
	-spice port="${spice}",addr=localhost,disable-ticketing=on \
	-device virtio-serial-pci \
	-device virtserialport,chardev=spicechannel0,name=com.redhat.spice.0 \
	-chardev spicevmc,id=spicechannel0,name=vdagent \
	-object rng-random,filename=/dev/urandom,id=rng0 \
	-device virtio-rng-pci,rng=rng0 \
	-usb \
	-device usb-tablet,bus=usb-bus.0 \
	-device ich9-intel-hda,addr=1f.1 \
	-audiodev spice,id=snd0 \
	-device hda-output,audiodev=snd0 \
	"$@" >"${vm}.out" 2>&1
